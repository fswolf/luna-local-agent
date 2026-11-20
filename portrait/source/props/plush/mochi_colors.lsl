// Mochi's colours: drop into the uploaded plushie, it paints each face and removes itself.
default
{
    state_entry()
    {
        llSetLinkPrimitiveParamsFast(LINK_THIS, [
            PRIM_COLOR, 0, <0.722, 0.643, 0.925>, 1.0,   // fur
            PRIM_COLOR, 1, <0.961, 0.639, 0.769>, 1.0,   // pink (ears, paws)
            PRIM_COLOR, 2, <0.169, 0.102, 0.200>, 1.0,   // eyes
            PRIM_COLOR, 3, <1.0, 1.0, 1.0>, 1.0,         // eye shine
            PRIM_FULLBRIGHT, 3, TRUE,
            PRIM_COLOR, 4, <0.969, 0.698, 0.800>, 1.0    // blush
        ]);
        llRemoveInventory(llGetScriptName());
    }
}
