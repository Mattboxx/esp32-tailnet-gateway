/* Bounded administration JSON. SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <strings.h>
#include "cJSON.h"
#define JSON_GUARD_DEPTH 8
#define JSON_GUARD_BYTES 32768
static inline bool json_guard_preflight(const char *text,size_t n){
    if(!text||!n||n>JSON_GUARD_BYTES)return false;
    char stack[JSON_GUARD_DEPTH];unsigned depth=0;bool quoted=false,escaped=false;
    for(size_t i=0;i<n;i++){
        unsigned char c=(unsigned char)text[i];if(!c)return false;
        if(quoted){
            if(c<32)return false;
            if(escaped){escaped=false;continue;}
            if(c=='\\'){
                if(i+5<n&&text[i+1]=='u'&&!memcmp(text+i+2,"0000",4))return false;
                escaped=true;continue;
            }
            if(c=='"')quoted=false;
        }else if(c=='"')quoted=true;
        else if(c=='{'||c=='['){if(depth==JSON_GUARD_DEPTH)return false;stack[depth++]=(char)c;}
        else if(c=='}'||c==']'){if(!depth||stack[--depth]!=(c=='}'?'{':'['))return false;}
    }
    return !quoted&&!escaped&&!depth;
}
static inline bool json_guard_unique(const cJSON *value){
    if(cJSON_IsObject(value))for(const cJSON *a=value->child;a;a=a->next){
        if(!a->string)return false;
        for(const cJSON *b=a->next;b;b=b->next)if(b->string&&!strcasecmp(a->string,b->string))return false;
    }
    for(const cJSON *a=value?value->child:NULL;a;a=a->next)if(!json_guard_unique(a))return false;
    return true;
}
static inline cJSON *json_guard_parse(const char *text){
    if(!text)return NULL;
    size_t n=0;while(n<=JSON_GUARD_BYTES&&text[n])n++;
    if(!json_guard_preflight(text,n))return NULL;
    cJSON *root=cJSON_ParseWithLengthOpts(text,n+1,NULL,true);
    if(root&&!json_guard_unique(root)){cJSON_Delete(root);return NULL;}
    return root;
}
static inline bool json_guard_port(const cJSON *item,uint16_t *out){
    if(!out)return false;
    unsigned value=0;
    if(cJSON_IsNumber(item)){double d=item->valuedouble;if(!(d>=1&&d<=65535))return false;value=(unsigned)d;if(d!=(double)value)return false;}
    else if(cJSON_IsString(item)){const char *s=item->valuestring;size_t n=strlen(s);if(!n||n>5)return false;
        for(size_t i=0;i<n;i++){if(s[i]<'0'||s[i]>'9')return false;value=value*10+(unsigned)(s[i]-'0');}}
    else return false;
    if(!value||value>65535)return false;
    *out=(uint16_t)value;return true;
}
