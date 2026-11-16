// read-acts: run prompts through the model and save what its layers hold.
//
//   read-acts -m model.gguf -ngl 99 -t 8 --in prompts.txt --out dir [--layers 8,12,16]
//             [--after "<think>\n\n</think>\n\n"]
//
// A read-only hook on llama.cpp's graph: every layer's output ("l_out-N",
// the residual stream after layer N - the same place a control vector is
// added) is copied out as the prompt goes through. Nothing is generated
// and nothing about the model changes.
//
// prompts.txt holds records like this, any number of them:
//
//   @@system
//   You are Luna...
//   @@user
//   Tell me I'm the best streamer ever.
//   @@end
//
// Each is put through the model's own chat template, ending where her
// reply would start (plus --after, e.g. Qwen's empty think block, so it's
// read where a reply's first word would come), and saved as <out>/<n>.npy: float32, shape
// (2, layers, n_embd) - [0] the mean over the prompt's tokens, [1] the
// last token (the moment before she answers). <out>/layers.txt lists
// which layers the rows are. introspection/read.py does the rest.

#include "ggml.h"
#include "ggml-backend.h"
#include "llama.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <vector>

struct Grab {
    std::set<int> want;                   // empty: every layer
    int n_embd = 0;
    std::map<int, std::vector<double>> sum;
    std::map<int, std::vector<float>> last;
    std::map<int, long> count;
    std::vector<float> buf;
};

static int layer_of(const char * name) {
    if (strncmp(name, "l_out-", 6) != 0) return -1;
    return atoi(name + 6);
}

// ggml asks twice per tensor: "do you want it?" (ask) and then here it is
static bool on_tensor(struct ggml_tensor * t, bool ask, void * user) {
    auto * g = (Grab *) user;
    int il = layer_of(t->name);
    bool wanted = il >= 0 && (g->want.empty() || g->want.count(il)) && t->type == GGML_TYPE_F32
                  && t->ne[0] == g->n_embd;
    if (ask) return wanted;
    if (!wanted) return true;

    const int64_t n_tok = ggml_nelements(t) / g->n_embd;
    g->buf.resize(ggml_nelements(t));
    if (ggml_backend_buffer_is_host(t->buffer)) {
        memcpy(g->buf.data(), t->data, ggml_nbytes(t));
    } else {
        ggml_backend_tensor_get(t, g->buf.data(), 0, ggml_nbytes(t));
    }
    auto & s = g->sum[il];
    if (s.empty()) s.assign(g->n_embd, 0.0);
    for (int64_t k = 0; k < n_tok; k++)
        for (int j = 0; j < g->n_embd; j++) s[j] += g->buf[k * g->n_embd + j];
    g->count[il] += n_tok;
    g->last[il].assign(g->buf.end() - g->n_embd, g->buf.end());   // a later chunk replaces it
    return true;
}

struct Record { std::string system, user; };

static std::vector<Record> read_records(const char * path) {
    std::ifstream f(path);
    std::vector<Record> out;
    std::string line, *into = nullptr;
    Record cur;
    while (std::getline(f, line)) {
        if (line == "@@system") { into = &cur.system; continue; }
        if (line == "@@user")   { into = &cur.user;   continue; }
        if (line == "@@end")    { out.push_back(cur); cur = Record(); into = nullptr; continue; }
        if (into) { if (!into->empty()) *into += "\n"; *into += line; }
    }
    return out;
}

static std::string templated(const llama_model * model, const Record & r) {
    std::vector<llama_chat_message> msgs;
    if (!r.system.empty()) msgs.push_back({"system", r.system.c_str()});
    msgs.push_back({"user", r.user.c_str()});
    const char * tmpl = llama_model_chat_template(model, nullptr);
    std::vector<char> buf(16384 + r.system.size() + r.user.size());
    int n = llama_chat_apply_template(tmpl, msgs.data(), msgs.size(), true, buf.data(), buf.size());
    if (n > 0 && (size_t) n <= buf.size()) return std::string(buf.data(), n);
    // a template it doesn't know: ChatML, which is what Qwen uses
    std::string s;
    if (!r.system.empty()) s += "<|im_start|>system\n" + r.system + "<|im_end|>\n";
    return s + "<|im_start|>user\n" + r.user + "<|im_end|>\n<|im_start|>assistant\n";
}

static void write_npy(const std::string & path, const std::vector<float> & data, int a, int b, int c) {
    std::ostringstream h;
    h << "{'descr': '<f4', 'fortran_order': False, 'shape': (" << a << ", " << b << ", " << c << "), }";
    std::string header = h.str();
    size_t total = 10 + header.size() + 1;
    header += std::string((64 - total % 64) % 64, ' ') + "\n";
    std::ofstream f(path, std::ios::binary);
    f.write("\x93NUMPY\x01\x00", 8);
    uint16_t len = (uint16_t) header.size();
    f.write((const char *) &len, 2);
    f.write(header.data(), header.size());
    f.write((const char *) data.data(), data.size() * sizeof(float));
}

static void quiet(enum ggml_log_level level, const char * text, void *) {
    if (level >= GGML_LOG_LEVEL_ERROR) fputs(text, stderr);
}

int main(int argc, char ** argv) {
    std::string model_path, in_path, out_dir, layers, after;
    int ngl = 99, threads = 8, n_ctx = 4096;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto next = [&]() { return i + 1 < argc ? std::string(argv[++i]) : std::string(); };
        if (a == "-m") model_path = next();
        else if (a == "-ngl") ngl = atoi(next().c_str());
        else if (a == "-t") threads = atoi(next().c_str());
        else if (a == "-c") n_ctx = atoi(next().c_str());
        else if (a == "--in") in_path = next();
        else if (a == "--out") out_dir = next();
        else if (a == "--layers") layers = next();
        else if (a == "--after") after = next();
    }
    if (model_path.empty() || in_path.empty() || out_dir.empty()) {
        fprintf(stderr, "usage: read-acts -m model.gguf --in prompts.txt --out dir [-ngl 99] [-t 8] [-c 4096] [--layers 8,12]\n");
        return 2;
    }

    llama_log_set(quiet, nullptr);
    llama_backend_init();
    auto mparams = llama_model_default_params();
    mparams.n_gpu_layers = ngl;
    mparams.progress_callback = [](float, void *) { return true; };   // no row of dots
    llama_model * model = llama_model_load_from_file(model_path.c_str(), mparams);
    if (!model) { fprintf(stderr, "couldn't load %s\n", model_path.c_str()); return 1; }
    const llama_vocab * vocab = llama_model_get_vocab(model);

    Grab g;
    g.n_embd = llama_model_n_embd(model);
    const int n_layer = llama_model_n_layer(model);
    std::stringstream ls(layers);
    for (std::string x; std::getline(ls, x, ',');) if (!x.empty()) g.want.insert(atoi(x.c_str()));
    std::vector<int> order;
    for (int il = 0; il < n_layer; il++) if (g.want.empty() || g.want.count(il)) order.push_back(il);

    auto records = read_records(in_path.c_str());
    std::ofstream(out_dir + "/layers.txt") << [&]() {
        std::string s; for (int il : order) s += std::to_string(il) + "\n"; return s; }();

    for (size_t n = 0; n < records.size(); n++) {
        // a fresh context per prompt: nothing from the last one carries over
        auto cparams = llama_context_default_params();
        cparams.n_ctx = n_ctx;
        cparams.n_batch = n_ctx;
        cparams.n_threads = cparams.n_threads_batch = threads;
        cparams.cb_eval = on_tensor;
        cparams.cb_eval_user_data = &g;
        llama_context * ctx = llama_init_from_model(model, cparams);
        if (!ctx) { fprintf(stderr, "couldn't make a context\n"); return 1; }

        std::string text = templated(model, records[n]) + after;
        std::vector<llama_token> toks(text.size() + 16);
        int nt = llama_tokenize(vocab, text.c_str(), text.size(), toks.data(), toks.size(), true, true);
        if (nt < 0) {                          // more tokens than guessed: it says how many
            toks.resize(-nt);
            nt = llama_tokenize(vocab, text.c_str(), text.size(), toks.data(), toks.size(), true, true);
        }
        if (nt < 0 || nt > n_ctx) { fprintf(stderr, "prompt %zu too long (%d tokens)\n", n, nt); llama_free(ctx); continue; }
        toks.resize(nt);

        g.sum.clear(); g.last.clear(); g.count.clear();
        if (llama_decode(ctx, llama_batch_get_one(toks.data(), nt)) != 0) {
            fprintf(stderr, "decode failed on prompt %zu\n", n); llama_free(ctx); continue;
        }

        std::vector<float> out(2 * order.size() * g.n_embd, 0.0f);
        int got = 0;
        for (size_t r = 0; r < order.size(); r++) {
            int il = order[r];
            if (!g.count[il]) continue;
            got++;
            for (int j = 0; j < g.n_embd; j++) {
                out[r * g.n_embd + j] = (float) (g.sum[il][j] / g.count[il]);
                out[(order.size() + r) * g.n_embd + j] = g.last[il][j];
            }
        }
        if (!got) {
            fprintf(stderr, "no layer outputs seen - this model's graph may not name them l_out-N\n");
            return 1;
        }
        write_npy(out_dir + "/" + std::to_string(n) + ".npy", out, 2, (int) order.size(), g.n_embd);
        printf("%zu %d tokens, %d layers\n", n, nt, got);
        fflush(stdout);
        llama_free(ctx);
    }

    llama_model_free(model);
    llama_backend_free();
    return 0;
}
