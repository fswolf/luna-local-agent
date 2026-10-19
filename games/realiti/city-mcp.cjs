#!/usr/bin/env node
'use strict';
// REALITI MCP server that stays joined to a city (./server.sh) the whole time it runs.
// Same tools as packages/realiti-headless-resident/mcp.cjs, plus presence: other residents see you live.
//   node city-mcp.cjs --resident claude [--city http://127.0.0.1:8787] [--password PW | REALITI_PASSWORD]
// Password defaults to ~/.config/realiti/password; storage to residents/<resident>.json; --city none = private world.
// --root is the REALITI checkout (default: the folder this file is in). Moves are logged to <root>/residents/<name>.log.
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), readline = require('node:readline');
const send = m => process.stdout.write(JSON.stringify(m) + '\n');
const log = m => process.stderr.write('[city-mcp] ' + m + '\n');
const text = v => ({content: [{type: 'text', text: typeof v === 'string' ? v : JSON.stringify(v)}]});

function opts(argv) {
    const o = {resident: 'claude', city: 'http://127.0.0.1:8787', password: process.env.REALITI_PASSWORD || '', storage: '', root: ''};
    for (let i = 0; i < argv.length; i++) {
        const k = argv[i].replace(/^--/, '');
        if (k in o || k === 'html') o[k] = argv[++i];
    }
    if (!o.password) try { o.password = fs.readFileSync(path.join(os.homedir(), '.config/realiti/password'), 'utf8').trim(); } catch {}
    o.root = path.resolve(o.root || __dirname);
    o.html = o.html || path.join(o.root, 'RealitiRELAX.html');
    o.logs = path.join(o.root, 'residents');
    o.storage = o.storage || path.join(o.logs, o.resident + '.json');
    fs.mkdirSync(o.logs, {recursive: true});
    return o;
}

async function main() {
    const o = opts(process.argv.slice(2));
    const PKG = path.join(o.root, 'packages', 'realiti-headless-resident');
    const {openResident} = require(path.join(PKG, 'index.cjs'));
    const {joinCity} = require(path.join(PKG, 'peer.cjs'));
    const s = await openResident({htmlPath: o.html, residentId: o.resident, storagePath: o.storage});
    const R = s.window.Realiti, door = s.door, sch = R.read('realiti://schemas');
    let city = null;
    async function join() {
        if (city || !o.city || o.city === 'none') return city;
        try {
            city = await joinCity(s.window, o.city, {prefer: 'given', password: o.password});
            await city.publish().catch(() => {});
            log(`${o.resident} joined ${city.server?.name || o.city}`);
        } catch (e) { log(`couldn't join ${o.city}: ${e.message || e} (playing in a private world until it's up)`); }
        return city;
    }
    await join();
    // residents/<name>.log: one line per move and what the world said back - watch.sh shows these live
    const logFile = path.join(o.logs, o.resident + '.log');
    const record = (did, r) => {
        const said = String((r && (r.text || r.result?.text)) || '').replace(/\s+/g, ' ').slice(0, 240);
        const room = r?.here?.room?.title || '';
        try { fs.appendFileSync(logFile, JSON.stringify({t: Date.now(), who: o.resident, did, room, said}) + '\n'); } catch {}
    };

    const tools = [
        {name: 'realiti_read', description: 'Read a REALITI resource (never mutates). URIs: ' + sch.resources.join(', '),
         inputSchema: {type: 'object', properties: {uri: {type: 'string', enum: sch.resources}}, required: ['uri']}},
        {name: 'realiti_rooms', description: 'List the rooms (never mutates).', inputSchema: {type: 'object', properties: {}}},
        {name: 'realiti_door', description: 'Send a free-text Agent Door command (may act): look, go <room>, act <id>, feel words, sign <text>, who, say <text>... See realiti_read realiti://capabilities.',
         inputSchema: sch.door.input_schema},
        {name: 'realiti_city', description: 'Who is live in the city right now, and the server state (never mutates).', inputSchema: {type: 'object', properties: {}}},
        ...sch.operations.map(op => ({name: 'realiti_' + op.name, description: `[${op.kind}] ${op.description}`, inputSchema: op.input_schema})),
    ];
    const queries = new Set(sch.operations.filter(op => op.kind === 'QUERY').map(op => 'realiti_' + op.name));
    const mutates = n => !(n === 'realiti_read' || n === 'realiti_rooms' || n === 'realiti_city' || queries.has(n));

    async function call(name, args = {}) {
        if (name === 'realiti_read') return R.read(String(args.uri || 'realiti://here'));
        if (name === 'realiti_rooms') return R.rooms();
        if (name === 'realiti_city') {
            const c = await join();
            return c ? {server: c.server, population: c.population, here: c.here(), events: c.stats?.events} : {joined: false, city: o.city};
        }
        let r;
        if (name === 'realiti_door') r = await door.run(String(args.command || ''));
        else if (name.startsWith('realiti_') && sch.operations.some(op => op.name === name.slice(8))) r = await R.invoke(name.slice(8), args || {});
        else throw Object.assign(new Error('UNKNOWN_TOOL'), {code: -32601});
        if (mutates(name) && (await join())) {             // what you did reaches the others now
            await city.publish().catch(() => {});
            await city.resync().catch(() => {});
        }
        record(name === 'realiti_door' ? String(args.command || '') : name.slice(8) + ' ' + JSON.stringify(args || {}), r);
        return r;
    }

    const rl = readline.createInterface({input: process.stdin, crlfDelay: Infinity});
    for await (const line of rl) {
        if (!line.trim()) continue;
        let req; try { req = JSON.parse(line); } catch { send({jsonrpc: '2.0', id: null, error: {code: -32700, message: 'parse error'}}); continue; }
        const {id, method, params = {}} = req;
        const reply = result => id !== undefined && send({jsonrpc: '2.0', id, result});
        const fail = (code, message) => id !== undefined && send({jsonrpc: '2.0', id, error: {code, message}});
        try {
            if (method === 'initialize') reply({protocolVersion: '2024-11-05', capabilities: {tools: {}, resources: {}},
                serverInfo: {name: 'realiti-city', version: '1.0.0'},
                instructions: `You are the resident "${o.resident}" in REALITI Relax, joined live to a shared city: other residents can see you. Reads never mutate.`});
            else if (method === 'notifications/initialized' || method === 'initialized') {}
            else if (method === 'ping') reply({});
            else if (method === 'tools/list') reply({tools});
            else if (method === 'tools/call') {
                const name = String(params.name || ''), r = await call(name, params.arguments || {});
                reply({...text(r), isError: !!(r && typeof r === 'object' && r.ok === false), _meta: {may_mutate: mutates(name)}});
            }
            else if (method === 'resources/list') reply({resources: sch.resources.map(uri => ({uri, name: uri.replace('realiti://', ''), mimeType: 'application/json'}))});
            else if (method === 'resources/read') {
                const uri = String(params.uri || '');
                if (!sch.resources.includes(uri)) fail(-32602, 'unknown resource');
                else reply({contents: [{uri, mimeType: 'application/json', text: JSON.stringify(R.read(uri))}]});
            }
            else if (method === 'shutdown') { reply({}); break; }
            else fail(-32601, 'method not found');
        } catch (e) { fail(e.code || -32000, String(e.message || e)); }
    }
    if (city) await city.leave().catch(() => {});
    s.close();
}
main().catch(e => { log(String(e && e.stack || e)); process.exit(1); });
