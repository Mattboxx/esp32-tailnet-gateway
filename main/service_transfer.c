/* Strict local preview/confirmed import. Imported listeners always start OFF.
 * Original implementation, Mattboxx Edition. SPDX-License-Identifier: MIT */
#include "service_transfer.h"
#include "tailnet_forward.h"
#include "forwarding_config.h"
#include "json_guard.h"
#include "web_ui.h"
#include "mqtt_integration.h"
#include "esp_heap_caps.h"
#include <stdlib.h>
#define TRANSFER_FORMAT "homelab-service-rules/v1"
static bool transfer_keys(const cJSON *o,const char *const *names,unsigned n){
    if(!cJSON_IsObject(o))return false;
    for(const cJSON *c=o->child;c;c=c->next){bool known=false;
        for(unsigned i=0;i<n;i++)if(c->string&&!strcmp(c->string,names[i]))known=true;
        if(!known)return false;
    }
    return true;
}
static esp_err_t transfer_parse(const cJSON *root,tailnet_forward_rule_t *rules,int *count){
    static const char *const root_keys[]={"format","rules","action","expected_guard","confirm_replace"};
    static const char *const rule_keys[]={"name","enabled","protocol","listen_port","tailnet_destination","destination_port","allowed_source_subnet"};
    const cJSON *format=cJSON_GetObjectItemCaseSensitive(root,"format"),*arr=cJSON_GetObjectItemCaseSensitive(root,"rules");
    if(!transfer_keys(root,root_keys,5)||!cJSON_IsString(format)||strcmp(format->valuestring,TRANSFER_FORMAT)
       ||!cJSON_IsArray(arr)||cJSON_GetArraySize(arr)>TAILNET_FORWARD_MAX)return ESP_ERR_INVALID_ARG;
    *count=cJSON_GetArraySize(arr);memset(rules,0,TAILNET_FORWARD_MAX*sizeof *rules);
    for(int i=0;i<*count;i++){
        const cJSON *j=cJSON_GetArrayItem(arr,i);if(!transfer_keys(j,rule_keys,7))return ESP_ERR_INVALID_ARG;
        const cJSON *name=cJSON_GetObjectItemCaseSensitive(j,"name"),*enabled=cJSON_GetObjectItemCaseSensitive(j,"enabled"),*proto=cJSON_GetObjectItemCaseSensitive(j,"protocol"),*dst=cJSON_GetObjectItemCaseSensitive(j,"tailnet_destination"),*src=cJSON_GetObjectItemCaseSensitive(j,"allowed_source_subnet");
        if(!cJSON_IsString(name)||strlen(name->valuestring)>=TAILNET_FORWARD_NAME_LEN||!cJSON_IsBool(enabled)
           ||!cJSON_IsString(proto)||!cJSON_IsString(dst)||strlen(dst->valuestring)>=TAILNET_FORWARD_DEST_LEN||!cJSON_IsString(src))return ESP_ERR_INVALID_ARG;
        tailnet_forward_rule_t *r=&rules[i];r->valid=1;r->enabled=0;
        r->proto=!strcmp(proto->valuestring,"tcp")?6:!strcmp(proto->valuestring,"udp")?17:0;
        if(!r->proto||!json_guard_port(cJSON_GetObjectItemCaseSensitive(j,"listen_port"),&r->listen_port)
           ||!json_guard_port(cJSON_GetObjectItemCaseSensitive(j,"destination_port"),&r->destination_port)
           ||tailnet_forward_parse_cidr(src->valuestring,&r->source_network,&r->source_prefix)!=ESP_OK)return ESP_ERR_INVALID_ARG;
        memcpy(r->name,name->valuestring,strlen(name->valuestring)+1);memcpy(r->destination,dst->valuestring,strlen(dst->valuestring)+1);
    }
    return ESP_OK;
}
static cJSON *transfer_json(const tailnet_forward_rule_t *rules,int count){
    cJSON *root=cJSON_CreateObject();if(!root)return NULL;
    cJSON *arr=cJSON_AddArrayToObject(root,"rules");
    if(!arr||!cJSON_AddStringToObject(root,"format",TRANSFER_FORMAT))goto failed;
    for(int i=0;i<count;i++){
        cJSON *j=cJSON_CreateObject();if(!j)goto failed;const tailnet_forward_rule_t *r=&rules[i];char cidr[32];
        tailnet_forward_format_cidr(r->source_network,r->source_prefix,cidr,sizeof cidr);
        bool ok=cJSON_AddStringToObject(j,"name",r->name)&&cJSON_AddBoolToObject(j,"enabled",r->enabled)
            &&cJSON_AddStringToObject(j,"protocol",r->proto==6?"tcp":"udp")&&cJSON_AddNumberToObject(j,"listen_port",r->listen_port)
            &&cJSON_AddStringToObject(j,"tailnet_destination",r->destination)&&cJSON_AddNumberToObject(j,"destination_port",r->destination_port)
            &&cJSON_AddStringToObject(j,"allowed_source_subnet",cidr);
        if(!ok||!cJSON_AddItemToArray(arr,j)){cJSON_Delete(j);goto failed;}
    }
    return root;
failed:cJSON_Delete(root);return NULL;
}
static esp_err_t transfer_send(httpd_req_t *req,cJSON *root){
    if(!root){httpd_resp_send_500(req);return ESP_FAIL;}
    char *text=cJSON_PrintUnformatted(root);cJSON_Delete(root);if(!text){httpd_resp_send_500(req);return ESP_FAIL;}
    httpd_resp_set_type(req,"application/json");httpd_resp_set_hdr(req,"Cache-Control","no-store");
    esp_err_t err=httpd_resp_sendstr(req,text);free(text);return err;
}
static esp_err_t transfer_export(httpd_req_t *req){
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    tailnet_forward_rule_t *rules=heap_caps_calloc(TAILNET_FORWARD_MAX,sizeof *rules,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!rules){httpd_resp_send_500(req);return ESP_FAIL;}
    forwarding_config_lock();int count=tailnet_forward_count();bool ok=true;
    for(int i=0;i<count;i++)if(!tailnet_forward_get(i,&rules[i],NULL))ok=false;
    forwarding_config_unlock();cJSON *root=ok?transfer_json(rules,count):NULL;free(rules);
    httpd_resp_set_hdr(req,"Content-Disposition","attachment; filename=homelab-service-rules.json");return transfer_send(req,root);
}
static esp_err_t transfer_import(httpd_req_t *req){
    if(web_ui_require_auth(req)!=ESP_OK)return ESP_FAIL;
    if(req->content_len<2||req->content_len>8192){httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid import size");return ESP_FAIL;}
    char *body=heap_caps_calloc(1,(size_t)req->content_len+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    tailnet_forward_rule_t *rules=heap_caps_calloc(TAILNET_FORWARD_MAX,sizeof *rules,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!body||!rules){free(body);free(rules);httpd_resp_send_500(req);return ESP_FAIL;}
    int n=0;while(n<req->content_len){int got=httpd_req_recv(req,body+n,req->content_len-n);if(got<=0){free(body);free(rules);httpd_resp_send_408(req);return ESP_FAIL;}n+=got;}
    cJSON *root=json_guard_preflight(body,(size_t)n)?json_guard_parse(body):NULL;free(body);
    int count=0;esp_err_t err=transfer_parse(root,rules,&count);
    const cJSON *action=cJSON_GetObjectItemCaseSensitive(root,"action"),*guard=cJSON_GetObjectItemCaseSensitive(root,"expected_guard"),*confirmed=cJSON_GetObjectItemCaseSensitive(root,"confirm_replace");
    bool apply=cJSON_IsString(action)&&!strcmp(action->valuestring,"apply");
    if(!cJSON_IsString(action)||(strcmp(action->valuestring,"preview")&&!apply)
       ||(apply&&(!cJSON_IsTrue(confirmed)||!cJSON_IsString(guard)||strlen(guard->valuestring)!=TAILNET_TABLE_GUARD_LEN-1)))err=ESP_ERR_INVALID_ARG;
    tailnet_forward_preview_t preview={0};char why[128]="Import validation or save failed; reload before retrying";
    if(err==ESP_OK)err=tailnet_forward_replace_guarded(rules,count,apply?guard->valuestring:NULL,apply,&preview,why,sizeof why);
    cJSON_Delete(root);
    cJSON *reply=err==ESP_OK?transfer_json(rules,count):cJSON_CreateObject();free(rules);
    if(!reply){httpd_resp_send_500(req);return ESP_FAIL;}
    cJSON_AddBoolToObject(reply,"ok",err==ESP_OK);
    if(err==ESP_OK){cJSON_AddBoolToObject(reply,"applied",apply);cJSON_AddStringToObject(reply,"expected_guard",preview.guard);
        cJSON_AddNumberToObject(reply,"previous_count",preview.previous_count);cJSON_AddNumberToObject(reply,"previous_enabled",preview.previous_enabled);
        cJSON_AddStringToObject(reply,"exposure","All imported listeners are disabled. Existing saved rules are replaced only after confirmation.");
        if(apply)mqtt_integration_tailnet_forward_changed();
    }else{httpd_resp_set_status(req,err==ESP_ERR_INVALID_ARG?"400 Bad Request":err==ESP_ERR_INVALID_STATE?"409 Conflict":"500 Internal Server Error");cJSON_AddStringToObject(reply,"error",why);}
    return transfer_send(req,reply);
}
esp_err_t service_transfer_register_http(httpd_handle_t server){
    const httpd_uri_t routes[]={{.uri="/api/tailnet-forward/export",.method=HTTP_GET,.handler=transfer_export},
        {.uri="/api/tailnet-forward/import",.method=HTTP_POST,.handler=transfer_import}};
    for(unsigned i=0;i<2;i++){esp_err_t e=httpd_register_uri_handler(server,&routes[i]);if(e!=ESP_OK)return e;}
    return ESP_OK;
}
