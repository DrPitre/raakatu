/*
 * decompile.c -- dump raaka-tu's packed game data (rooms, objects, command
 * scripts, vocabulary) as readable pseudocode.
 *
 * This is a scoping tool for porting the game to another engine (e.g.
 * Inform 6 / Z-machine): it decodes the same tables raakatu.c interprets
 * at runtime, but only prints them -- it does not run the game. Numeric
 * room/object/vocab references are left as-is (raaka-tu.asm has no names
 * for them either).
 */
#include <stdio.h>
#include <string.h>

typedef unsigned char byte;
typedef unsigned short word;

extern byte chartab[];
extern byte phrase_list[];
extern byte room_data[];
extern byte obj_data[];
extern byte cmd_data[];
extern byte ccmd_data[];
extern byte vocab_data[];
extern byte prep_data[];

/* ---- shared list helpers (mirror raakatu.c) ----------------------------- */

static byte *list_end_from_len(byte *p, byte **content)
{
    word len;
    if (*p & 0x80) {
        len = ((word)(*p & 0x7F) << 8) | *(p + 1);
        *content = p + 2;
    } else {
        len = *p;
        *content = p + 1;
    }
    return *content + len;
}

static byte *list_open(byte *p, byte **content_out)
{
    return list_end_from_len(p + 1, content_out);
}

static byte *list_begin(byte *list, byte **base_end)
{
    byte *content;
    *base_end = list_open(list, &content);
    return content;
}

/* ---- base-40 packed text decode ----------------------------------------- */

static void decode_packed_range(byte *content, byte *end, char *out, size_t outsz)
{
    word remaining = (word)(end - content);
    size_t oi = 0;

    while (remaining >= 2 && oi + 3 < outsz) {
        word v = ((word)content[1] << 8) | content[0];
        byte decoded[3];
        int i;
        decoded[0] = chartab[v / 1600];
        decoded[1] = chartab[(v / 40) % 40];
        decoded[2] = chartab[v % 40];
        for (i = 0; i < 3; i++) {
            byte c = decoded[i];
            out[oi++] = (c == 0xCF) ? '^' : (char)c;
        }
        content += 2;
        remaining -= 2;
    }
    if (remaining == 1 && oi + 1 < outsz)
        out[oi++] = (char)*content;
    out[oi] = '\0';
}

/* ---- opcode table (mirrors optable[] in raakatu.c) ---------------------- */

enum { K_PLAIN, K_MSG, K_DISPATCH, K_DOLIST, K_DOLISTALL, K_DOLISTNOT };

typedef struct { const char *name; int operand_bytes; int kind; } OpInfo;

#define NUM_OPS 0x27

static OpInfo optab[NUM_OPS] = {
    { "GoRoomPrint",           1, K_PLAIN },      /* 0x00 */
    { "CheckObj",              1, K_PLAIN },      /* 0x01 */
    { "IsOwnedByActive",       1, K_PLAIN },      /* 0x02 */
    { "CmpObjRoom",            2, K_PLAIN },      /* 0x03 */
    { "PrintMsg",              0, K_MSG },        /* 0x04 */
    { "CmpRand",               1, K_PLAIN },      /* 0x05 */
    { "PrintInvent",           0, K_PLAIN },      /* 0x06 */
    { "PrintRoom",             0, K_PLAIN },      /* 0x07 */
    { "IsFirstNoun",           1, K_PLAIN },      /* 0x08 */
    { "IsSecondNoun",          1, K_PLAIN },      /* 0x09 */
    { "TestPhrase",            1, K_PLAIN },      /* 0x0A */
    { "Dispatch",              0, K_DISPATCH },   /* 0x0B */
    { "RetFalse",              0, K_PLAIN },      /* 0x0C */
    { "DoList(AND)",           0, K_DOLIST },     /* 0x0D */
    { "DoListAll(OR)",         0, K_DOLISTALL },  /* 0x0E */
    { "SetObjRoomActive",      0, K_PLAIN },      /* 0x0F */
    { "DropObj",               0, K_PLAIN },      /* 0x10 */
    { "PrintNoun1",            0, K_PLAIN },      /* 0x11 */
    { "PrintNoun2",            0, K_PLAIN },      /* 0x12 */
    { "RunObjScripts",         0, K_PLAIN },      /* 0x13 */
    { "Not",                   0, K_DOLISTNOT },  /* 0x14 */
    { "TestObjBit",            1, K_PLAIN },      /* 0x15 */
    { "PrintVarObj",           0, K_PLAIN },      /* 0x16 */
    { "MoveTo",                2, K_PLAIN },      /* 0x17 */
    { "IsVarObjOwnedByActive", 0, K_PLAIN },      /* 0x18 */
    { "GoRoom",                1, K_PLAIN },      /* 0x19 */
    { "SetVarNoun1",           0, K_PLAIN },      /* 0x1A */
    { "SetVarNoun2",           0, K_PLAIN },      /* 0x1B */
    { "SetVarObj",             1, K_PLAIN },      /* 0x1C */
    { "Damage",                1, K_PLAIN },      /* 0x1D */
    { "SwapObjRooms",          2, K_PLAIN },      /* 0x1E */
    { "Print2",                0, K_MSG },        /* 0x1F */
    { "ChkActiveRoom",         1, K_PLAIN },      /* 0x20 */
    { "SubScript",             3, K_PLAIN },      /* 0x21 */
    { "HPGreaterThan",         1, K_PLAIN },      /* 0x22 */
    { "AddHP",                 1, K_PLAIN },      /* 0x23 */
    { "Halt",                  0, K_PLAIN },      /* 0x24 */
    { "Restart",               0, K_PLAIN },      /* 0x25 */
    { "PrintScore",            0, K_PLAIN },      /* 0x26 */
};

/* ---- pseudocode disassembler --------------------------------------------- */

static void ind(int n) { while (n-- > 0) fputs("  ", stdout); }

static void disasm_script(byte *p, byte *end, int indent);
static void disasm_one(byte **pp, byte *end, int indent);

/* Describe the opcode `op` whose operands begin at *pp; does not read an
 * opcode byte itself (caller already knows `op`, e.g. from a Dispatch test
 * slot) and does not indent its own first line. */
static void describe_op_body(byte op, byte **pp, byte *end, int indent)
{
    OpInfo *oi = &optab[op];

    switch (oi->kind) {
    case K_MSG: {
        byte *content, *me = list_end_from_len(*pp, &content);
        char buf[256];
        decode_packed_range(content, me, buf, sizeof buf);
        printf("%s \"%s\"\n", oi->name, buf);
        *pp = me;
        break;
    }
    case K_DISPATCH: {
        byte *content, *se = list_end_from_len(*pp, &content);
        byte test_op = *content++;
        byte *item = content;
        int caseno = 0;
        *pp = se;
        printf("Dispatch:\n");
        while (item < se) {
            byte *test_pp = item;
            byte *action_content, *ae;
            ind(indent + 1);
            printf("case %d: if ", caseno++);
            if (test_op < NUM_OPS)
                describe_op_body(test_op, &test_pp, se, indent + 1);
            else
                printf("<bad test opcode 0x%02X>\n", test_op);
            item = test_pp;
            ae = list_end_from_len(item, &action_content);
            ind(indent + 1);
            printf("  then:\n");
            {
                byte *aip = action_content;
                disasm_one(&aip, ae, indent + 2);
            }
            item = ae;
        }
        break;
    }
    case K_DOLIST:
    case K_DOLISTALL: {
        byte *content, *se = list_end_from_len(*pp, &content);
        byte *item = content;
        *pp = se;
        printf("%s:\n", oi->kind == K_DOLIST ? "AND (all must succeed)" : "OR (first success wins)");
        while (item < se)
            disasm_one(&item, se, indent + 1);
        break;
    }
    case K_DOLISTNOT:
        printf("NOT:\n");
        disasm_one(pp, end, indent + 1);
        break;
    default: {
        int k;
        printf("%s", oi->name);
        if (oi->operand_bytes) {
            printf("(");
            for (k = 0; k < oi->operand_bytes; k++)
                printf("%s0x%02X", k ? "," : "", (*pp)[k]);
            printf(")");
        }
        printf("\n");
        *pp += oi->operand_bytes;
        break;
    }
    }
}

static void disasm_one(byte **pp, byte *end, int indent)
{
    byte op = *(*pp)++;

    ind(indent);
    if (op & 0x80) {
        printf("CommonCmd(0x%02X)\n", op);
        return;
    }
    if (op >= NUM_OPS) {
        byte block_size = *(*pp)++;
        byte *bs = *pp, *be = bs + block_size;
        *pp = be;
        printf("IfPhraseForm(0x%02X):\n", op);
        disasm_script(bs, be, indent + 1);
        return;
    }
    describe_op_body(op, pp, end, indent);
}

static void disasm_script(byte *p, byte *end, int indent)
{
    while (p < end)
        disasm_one(&p, end, indent);
}

/* ---- top-level table dumps ------------------------------------------------ */

/* Sublist tags seen inside room_data / obj_data items:
 *   0x02 object short name (text)   0x03 description (text)
 *   0x04 room command script        0x06 noun2 command script
 *   0x07 noun1 command script       0x08 turn (per-move) script
 *   0x09 hit-point block            0x0A death script
 * Anything else is dumped as a script on a best-effort basis. */
static void dump_sublists(byte *content, byte *end, int indent)
{
    byte *p = content;
    while (p < end) {
        byte tag = *p;
        byte *sc, *se = list_open(p, &sc);
        ind(indent);
        printf("[tag 0x%02X] ", tag);
        switch (tag) {
        case 0x02:
        case 0x03: {
            char buf[256];
            decode_packed_range(sc, se, buf, sizeof buf);
            printf("text: \"%s\"\n", buf);
            break;
        }
        case 0x09: {
            byte *b;
            printf("hp-block: bytes =");
            for (b = sc; b < se; b++)
                printf(" 0x%02X", *b);
            printf("\n");
            break;
        }
        default:
            printf("script:\n");
            disasm_script(sc, se, indent + 1);
            break;
        }
        p = se;
    }
}

static void dump_rooms(void)
{
    byte *base_end;
    byte *p = list_begin(room_data, &base_end);

    printf("=========================== ROOMS ===========================\n\n");
    while (p < base_end) {
        byte tag = *p;
        byte *content, *item_end = list_open(p, &content);
        printf("=== Room 0x%02X ===\n", tag);
        printf("  flags=0x%02X\n", content[0]);
        dump_sublists(content + 1, item_end, 1);
        printf("\n");
        p = item_end;
    }
}

static void dump_objects(void)
{
    byte *base_end;
    byte *p = list_begin(obj_data, &base_end);
    int seq = 0;

    printf("=========================== OBJECTS ==========================\n\n");
    while (p < base_end) {
        byte tag = *p;
        byte *content, *item_end = list_open(p, &content);
        seq++;
        printf("=== Object #%d (vocab tag 0x%02X) ===\n", seq, tag);
        printf("  loc=0x%02X score=%d bits=0x%02X\n", content[0], content[1], content[2]);
        dump_sublists(content + 3, item_end, 1);
        printf("\n");
        p = item_end;
    }
}

static void dump_cmd_data(void)
{
    byte *cc, *ce = list_open(cmd_data, &cc);
    printf("======================= CMD_DATA (main dispatch) =============\n\n");
    disasm_script(cc, ce, 1);
    printf("\n");
}

static void dump_ccmd_data(void)
{
    byte *base_end;
    byte *p = list_begin(ccmd_data, &base_end);

    printf("======================= CCMD_DATA (common commands) ==========\n\n");
    while (p < base_end) {
        byte tag = *p;
        byte *content, *item_end = list_open(p, &content);
        printf("=== Common command 0x%02X ===\n", tag);
        disasm_script(content, item_end, 1);
        printf("\n");
        p = item_end;
    }
}

static void dump_vocab_list(byte *p, const char *label)
{
    printf("%s:\n", label);
    while (*p != 0) {
        byte wlen = *p++;
        printf("  \"%.*s\" -> word #%d\n", (int)wlen, (char *)p, p[wlen]);
        p += wlen + 1;
    }
}

static void dump_vocab(void)
{
    static const char *names[4] = { "ignore-words", "verbs", "nouns", "adjectives" };
    byte *p = vocab_data;
    int li;

    printf("========================= VOCABULARY ==========================\n\n");
    for (li = 0; li < 4; li++) {
        dump_vocab_list(p, names[li]);
        while (*p != 0) {
            byte wlen = *p++;
            p += wlen + 1;
        }
        p++;
    }
    dump_vocab_list(prep_data, "prepositions");
    printf("\n");
}

static void dump_phrase_list(void)
{
    byte *p = phrase_list;
    printf("======================= PHRASE_LIST ===========================\n\n");
    while (*p != 0) {
        printf("  verb=0x%02X prep=0x%02X n1mask=0x%02X n2mask=0x%02X -> form=0x%02X\n",
               p[0], p[1], p[2], p[3], p[4]);
        p += 5;
    }
    printf("\n");
}

int main(void)
{
    dump_vocab();
    dump_phrase_list();
    dump_rooms();
    dump_objects();
    dump_cmd_data();
    dump_ccmd_data();
    return 0;
}
