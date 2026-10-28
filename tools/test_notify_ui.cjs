// Actual notification-form controller with deterministic DOM/HTTP fixtures.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../main/index.html'),'utf8');
const start=html.indexOf('    var ntUi = (function () {');
const controller=html.slice(start,html.indexOf('    })();',start)+11);
const elements={},requests=[];
function el(id){return elements[id]||(elements[id]={value:'',checked:false,disabled:false,textContent:'',listeners:{},
  tagName:id.endsWith('events')||id.endsWith('security')?'SELECT':'INPUT',type:id.endsWith('enabled')||id.endsWith('clear')?'checkbox':'text',
  addEventListener(type,fn){this.listeners[type]=fn;}});}
const fields={tg:['enabled','token','clear','chat','events'],mail:['enabled','host','port','security','user','pass','from','to','events']};
const context={document:{getElementById:el,querySelectorAll(q){const ch=q.includes('nt-tg-')?'tg':'mail';return fields[ch].map(k=>el('nt-'+ch+'-'+k));}},
  clearTimeout(){},setTimeout(){return 1;},onPage(){return false;},showToast(){},
  apiFetch(url,opts){return new Promise(resolve=>requests.push({url,opts,resolve}));}};
vm.createContext(context);vm.runInContext(controller,context);
const response=d=>({status:200,ok:true,json:()=>Promise.resolve(d)});
const body=(chat='saved-chat')=>({events:'problems',waiting:1,telegram:{enabled:true,has_token:true,chat,sent:0,failed:0,last_error:''},
  email:{enabled:true,host:'saved.example',port:465,security:'tls',user:'',has_password:true,from:'',to:'',sent:0,failed:0,last_error:''}});
function input(id,value){const e=el(id);e.value=value;e.listeners[e.tagName==='SELECT'||e.type==='checkbox'?'change':'input'].call(e);}
const turn=()=>new Promise(setImmediate);
(async()=>{
  let load=context.ntUi.load();requests.shift().resolve(response(body()));await load;
  assert.equal(el('nt-tg-save').disabled,true);
  let old=context.ntUi.load(),fresh=context.ntUi.load();let a=requests.shift(),b=requests.shift();
  b.resolve(response(body('newer')));await fresh;a.resolve(response(body('stale')));await old;
  assert.equal(el('nt-tg-chat').value,'newer');
  input('nt-tg-chat','draft-chat');input('nt-tg-token','draft-token');input('nt-mail-pass','draft-password');
  load=context.ntUi.load();requests.shift().resolve(response(body('old')));await load;
  assert.equal(el('nt-tg-chat').value,'draft-chat');assert.equal(el('nt-tg-token').value,'draft-token');
  assert.equal(el('nt-mail-pass').value,'draft-password');
  el('nt-tg-save').listeners.click();assert.equal(el('nt-tg-save').disabled,true);
  const post=requests.shift();assert.equal(post.opts.method,'POST');
  input('nt-tg-token','newer-draft');assert.equal(el('nt-tg-save').disabled,true);
  el('nt-tg-save').listeners.click();assert.equal(requests.length,0,'duplicate save refused while a request is pending');
  post.resolve(response({ok:true}));await turn();requests.shift().resolve(response(body('draft-chat')));await turn();
  assert.equal(el('nt-tg-token').value,'newer-draft','newer input survives save completion');
  assert.equal(el('nt-tg-save').disabled,false);assert.equal(el('nt-mail-pass').value,'draft-password');
  assert.equal(el('nt-mail-save').disabled,false,'saving Telegram never discards email draft');
  load=context.ntUi.load();requests.shift().resolve(response({telegram:{},email:{}}));await load;
  assert.match(el('nt-tg-note').textContent,/Invalid notification settings response/);
  assert.equal(el('nt-tg-token').value,'newer-draft');
  console.log('PASS actual notification controller: stale read rejection, poll-safe drafts, no duplicate save, in-flight edits and separate channel state');
})().catch(e=>{console.error(e);process.exitCode=1;});
