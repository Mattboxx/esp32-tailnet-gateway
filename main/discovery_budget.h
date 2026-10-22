#pragma once
#include <stdbool.h>
#include <stdint.h>
/* One MQTT worker, deterministic enumeration, at most four new entities/pass. */
typedef struct {uint16_t cursor,ordinal;uint8_t budget;bool failed;} discovery_budget_t;
static inline void discovery_reset(discovery_budget_t *s){*s=(discovery_budget_t){0};}
static inline void discovery_begin(discovery_budget_t *s){s->ordinal=0;s->budget=4;s->failed=false;}
static inline bool discovery_visit(discovery_budget_t *s){
    unsigned index=s->ordinal++;
    return !s->failed && s->budget && index==s->cursor;
}
static inline void discovery_result(discovery_budget_t *s,bool accepted){
    if(!accepted)s->failed=true;
    else {s->cursor++;s->budget--;}
}
static inline bool discovery_finished(const discovery_budget_t *s){return !s->failed&&s->cursor>=s->ordinal;}
