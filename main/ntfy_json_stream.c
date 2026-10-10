/* Validate the entire JSON frame, retain only bounded top-level fields.
 * Unknown strings/containers do not require storage; no recursive calls,
 * cJSON allocations or dependence on HTTP chunk boundaries. */
#include "ntfy_json_stream.h"
#include <string.h>

enum { L_NONE, L_STRING, L_ESCAPE, L_UNICODE, L_LOW_SLASH, L_LOW_U, L_NUMBER, L_LITERAL };
enum { F_NONE, F_ID, F_EVENT, F_MESSAGE, F_TITLE };
enum { P_FIRST, P_REQUIRED, P_COLON, P_VALUE, P_END };
enum { N_SIGN, N_ZERO, N_INT, N_DOT, N_FRAC, N_EXP, N_EXP_SIGN, N_EXP_DIGIT };

static bool space(unsigned char b) { return b==' ' || b=='\t' || b=='\r' || b=='\n'; }
static bool command_space(unsigned char b) { return space(b) || b=='\v' || b=='\f'; }

void ntfy_json_reset(ntfy_json_parser_t *p) { memset(p, 0, sizeof *p); }
bool ntfy_json_finish(const ntfy_json_parser_t *p)
{ return p->done && !p->invalid && p->depth==0 && p->lex==L_NONE; }

static void emit(ntfy_json_parser_t *p, unsigned char b)
{
    /* Match command edge trimming without buffering unbounded whitespace. */
    bool command = !p->key && p->capture==F_MESSAGE;
    if (command && !p->used && command_space(b)) return;
    if (p->used < sizeof p->text-1) p->text[p->used++]=(char)b;
    else if (!command || !command_space(b)) p->overflow=true;
    if (command && !command_space(b)) p->trim_end=p->used;
}

static void emit_codepoint(ntfy_json_parser_t *p, uint32_t code)
{
    /* Embedded NUL would change command/key meaning in C strings. */
    if (!code) { p->invalid=true; return; }
    if (code < 0x80) emit(p, (unsigned char)code);
    else if (code < 0x800) { emit(p,0xc0|(code>>6));emit(p,0x80|(code&63)); }
    else if (code < 0x10000) {
        emit(p,0xe0|(code>>12));emit(p,0x80|((code>>6)&63));emit(p,0x80|(code&63));
    } else {
        emit(p,0xf0|(code>>18));emit(p,0x80|((code>>12)&63));
        emit(p,0x80|((code>>6)&63));emit(p,0x80|(code&63));
    }
}

static void copy_field(char *out, size_t size, const char *text, bool overflow)
{
    size_t length=strlen(text);
    if (overflow || length >= size) { out[0]=0;return; }
    memcpy(out,text,length+1);
}

static void end_string(ntfy_json_parser_t *p)
{
    p->text[p->used]=0;
    if (p->key) {
        p->field=F_NONE;
        if (p->depth==1 && !p->overflow) {
            if (!strcmp(p->text,"id"))p->field=F_ID;
            else if (!strcmp(p->text,"event"))p->field=F_EVENT;
            else if (!strcmp(p->text,"message"))p->field=F_MESSAGE;
            else if (!strcmp(p->text,"title"))p->field=F_TITLE;
            if (p->field) {
                uint8_t bit=(uint8_t)(1U<<p->field);
                if (p->seen&bit)p->invalid=true; /* Reject ambiguous duplicate fields. */
                p->seen|=bit;
            }
        }
        p->stack[p->depth-1].phase=P_COLON;
    } else switch (p->capture) {
        case F_ID: copy_field(p->event.id,sizeof p->event.id,p->text,p->overflow);break;
        case F_EVENT: copy_field(p->event.event,sizeof p->event.event,p->text,p->overflow);break;
        case F_MESSAGE:
            p->text[p->trim_end]=0;
            p->event.has_message=true;p->event.message_too_long=p->overflow;
            copy_field(p->event.message,sizeof p->event.message,p->text,p->overflow);break;
        case F_TITLE: {
            size_t n=p->used<6?p->used:6;
            memcpy(p->event.title,p->text,n);p->event.title[n]=0;break;
        }
        default: break;
    }
    p->lex=L_NONE;
}

static void begin_string(ntfy_json_parser_t *p, bool key, uint8_t capture)
{
    p->key=key;p->capture=capture;p->used=p->trim_end=0;p->overflow=false;
    p->utf8_left=0;p->high_surrogate=0;p->lex=L_STRING;
}

static bool raw_utf8(ntfy_json_parser_t *p, unsigned char b)
{
    if (p->utf8_left) {
        if (b<p->utf8_min || b>p->utf8_max)return false;
        p->utf8_left--;p->utf8_min=0x80;p->utf8_max=0xbf;return true;
    }
    if (b<0x80)return true;
    p->utf8_min=0x80;p->utf8_max=0xbf;
    if (b>=0xc2 && b<=0xdf)p->utf8_left=1;
    else if (b>=0xe0 && b<=0xef) {
        p->utf8_left=2;if(b==0xe0)p->utf8_min=0xa0;if(b==0xed)p->utf8_max=0x9f;
    } else if (b>=0xf0 && b<=0xf4) {
        p->utf8_left=3;if(b==0xf0)p->utf8_min=0x90;if(b==0xf4)p->utf8_max=0x8f;
    } else return false;
    return true;
}

static bool number_byte(ntfy_json_parser_t *p, unsigned char b)
{
    bool digit=b>='0' && b<='9';
    switch(p->number) {
        case N_SIGN: if(digit){p->number=b=='0'?N_ZERO:N_INT;return true;}break;
        case N_ZERO: if(b=='.'){p->number=N_DOT;return true;}if(b=='e'||b=='E'){p->number=N_EXP;return true;}break;
        case N_INT: if(digit)return true;if(b=='.'){p->number=N_DOT;return true;}if(b=='e'||b=='E'){p->number=N_EXP;return true;}break;
        case N_DOT: if(digit){p->number=N_FRAC;return true;}break;
        case N_FRAC: if(digit)return true;if(b=='e'||b=='E'){p->number=N_EXP;return true;}break;
        case N_EXP: if(b=='-'||b=='+'){p->number=N_EXP_SIGN;return true;}if(digit){p->number=N_EXP_DIGIT;return true;}break;
        case N_EXP_SIGN: if(digit){p->number=N_EXP_DIGIT;return true;}break;
        case N_EXP_DIGIT: if(digit)return true;break;
    }
    if (p->number!=N_ZERO && p->number!=N_INT && p->number!=N_FRAC && p->number!=N_EXP_DIGIT)
        p->invalid=true;
    p->lex=L_NONE;return false; /* Delimiter is checked by the container grammar. */
}

void ntfy_json_feed(ntfy_json_parser_t *p, unsigned char b)
{
    if(p->invalid)return;
    if(p->lex==L_STRING) {
        if(p->utf8_left) {
            if(!raw_utf8(p,b))p->invalid=true;else emit(p,b);
        } else if(b=='"')end_string(p);
        else if(b=='\\')p->lex=L_ESCAPE;
        else if(b<32 || !raw_utf8(p,b))p->invalid=true;
        else emit(p,b);
        return;
    }
    if(p->lex==L_ESCAPE) {
        unsigned char decoded=b;
        if(b=='u'){p->unicode=0;p->unicode_digits=0;p->lex=L_UNICODE;return;}
        if(b=='b')decoded='\b';else if(b=='f')decoded='\f';else if(b=='n')decoded='\n';
        else if(b=='r')decoded='\r';else if(b=='t')decoded='\t';
        else if(b!='"' && b!='\\' && b!='/'){p->invalid=true;return;}
        emit(p,decoded);p->lex=L_STRING;return;
    }
    if(p->lex==L_LOW_SLASH){if(b=='\\')p->lex=L_LOW_U;else p->invalid=true;return;}
    if(p->lex==L_LOW_U) {
        if(b=='u'){p->unicode=0;p->unicode_digits=0;p->lex=L_UNICODE;}else p->invalid=true;
        return;
    }
    if(p->lex==L_UNICODE) {
        unsigned v;
        if(b>='0'&&b<='9')v=b-'0';else if(b>='a'&&b<='f')v=b-'a'+10;
        else if(b>='A'&&b<='F')v=b-'A'+10;else {p->invalid=true;return;}
        p->unicode=(uint16_t)((p->unicode<<4)|v);
        if(++p->unicode_digits==4) {
            uint32_t code=p->unicode;
            if(p->high_surrogate) {
                if(code<0xdc00 || code>0xdfff){p->invalid=true;return;}
                code=0x10000+((p->high_surrogate-0xd800)<<10)+(code-0xdc00);
                p->high_surrogate=0;
            } else if(code>=0xd800 && code<=0xdbff) {
                p->high_surrogate=(uint16_t)code;p->lex=L_LOW_SLASH;return;
            } else if(code>=0xdc00 && code<=0xdfff){p->invalid=true;return;}
            emit_codepoint(p,code);p->lex=L_STRING;
        }
        return;
    }
    if(p->lex==L_LITERAL) {
        if(p->literal[p->literal_pos]) {
            if(b==(unsigned char)p->literal[p->literal_pos])p->literal_pos++;
            else p->invalid=true;
            return;
        }
        p->lex=L_NONE;
    } else if(p->lex==L_NUMBER && number_byte(p,b))return;
    if(p->invalid)return;
    if(space(b))return;
    if(!p->started) {
        if(b!='{'){p->invalid=true;return;}
        p->started=true;p->depth=1;p->stack[0].kind='{';return;
    }
    if(p->done || !p->depth){p->invalid=true;return;}
    uint8_t depth=p->depth-1, phase=p->stack[depth].phase, kind=p->stack[depth].kind;
    if(b=='}' || b==']') {
        if((b=='}' && kind!='{') || (b==']' && kind!='[') ||
           (phase!=P_FIRST && phase!=P_END)){p->invalid=true;return;}
        if(--p->depth==0)p->done=true;
        return;
    }
    if(phase==P_END) {
        if(b!=',')p->invalid=true;else p->stack[depth].phase=P_REQUIRED;
        return;
    }
    if(kind=='{' && (phase==P_FIRST || phase==P_REQUIRED)) {
        if(b!='"')p->invalid=true;else begin_string(p,true,F_NONE);
        return;
    }
    if(phase==P_COLON) {
        if(b!=':')p->invalid=true;else p->stack[depth].phase=P_VALUE;
        return;
    }
    if((kind=='{' && phase!=P_VALUE) ||
       (kind=='[' && phase!=P_FIRST && phase!=P_REQUIRED)){p->invalid=true;return;}
    uint8_t capture=p->depth==1?p->field:F_NONE;
    p->stack[depth].phase=P_END;
    if(b=='{' || b=='[') {
        if(p->depth>=sizeof p->stack/sizeof p->stack[0]){p->invalid=true;return;}
        p->stack[p->depth].kind=b;p->stack[p->depth++].phase=P_FIRST;
    } else if(b=='"')begin_string(p,false,capture);
    else if(b=='t'||b=='f'||b=='n') {
        p->lex=L_LITERAL;p->literal=b=='t'?"true":b=='f'?"false":"null";p->literal_pos=1;
    } else if(b=='-' || (b>='0'&&b<='9')) {
        p->lex=L_NUMBER;p->number=b=='-'?N_SIGN:b=='0'?N_ZERO:N_INT;
    } else p->invalid=true;
}
