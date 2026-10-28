// Actual notification-form controller with deterministic DOM/HTTP fixtures.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../main/index.html'),'utf8');
const start=html.indexOf('    var ntUi = (function () {');
const controller=html.slice(start,html.indexOf('    })();',start)+11);
const elements={},requests=[];
function el(id){return elements[id]||(elements[id]={value:'',checked:false,disabled:false,textContent:'',listeners:{},
  tagName:id.endsWith('events')||id.endsWith('security')?'SELECT':'INPUT',type:id.endsWith('enabled')||id.endsWith('clear')||id.endsWith('startup')||id.endsWith('poweron')?'checkbox':'text',
  addEventListener(type,fn){this.listeners[type]=fn;}});}
const fields={tg:['enabled','token','clear','chat','events','startup','poweron'],mail:['enabled','host','port','security','user','pass','from','to','events','startup','poweron']};
const context={document:{getElementById:el,querySelectorAll(q){const ch=q.includes('nt-tg-')?'tg':'mail';return fields[ch].map(k=>el('nt-'+ch+'-'+k));}},
  clearTimeout(){},setTimeout(){return 1;},onPage(){return false;},showToast(){},
  apiFetch(url,opts){return new Promise(resolve=>requests.push({url,opts,resolve}));}};
vm.createContext(context);vm.runInContext(controller,context);
const response=d=>({status:200,ok:true,json:()=>Promise.resolve(d)});
const body=(chat='saved-chat')=>({events:'problems',waiting:1,telegram:{enabled:true,notify_startup:true,notify_poweron:false,has_token:true,chat,sent:0,failed:0,last_error:''},
  email:{enabled:true,notify_startup:false,notify_poweron:true,host:'saved.example',port:465,security:'tls',user:'',has_password:true,from:'',to:'',sent:0,failed:0,last_error:''}});
function input(id,value){const e=el(id);e.value=value;e.listeners[e.tagName==='SELECT'||e.type==='checkbox'?'change':'input'].call(e);}
const turn=()=>new Promise(setImmediate);
(async()=>{
  let load=context.ntUi.load();requests.shift().resolve(response(body()));await load;
  assert.equal(el('nt-tg-startup').checked,true);assert.equal(el('nt-mail-startup').checked,false);
  assert.equal(el('nt-tg-save').disabled,true);
  let old=context.ntUi.load(),fresh=context.ntUi.load();let a=requests.shift(),b=requests.shift();
  b.resolve(response(body('newer')));await fresh;a.resolve(response(body('stale')));await old;
  assert.equal(el('nt-tg-chat').value,'newer');
  el('nt-tg-poweron').checked=true;input('nt-tg-poweron','');
  el('nt-tg-startup').checked=false;input('nt-tg-startup','');
  el('nt-mail-startup').checked=true;input('nt-mail-startup','');
  input('nt-tg-chat','draft-chat');input('nt-tg-token','draft-token');input('nt-mail-pass','draft-password');
  load=context.ntUi.load();requests.shift().resolve(response(body('old')));await load;
  assert.equal(el('nt-tg-chat').value,'draft-chat');assert.equal(el('nt-tg-token').value,'draft-token');
  assert.equal(el('nt-mail-pass').value,'draft-password');
  assert.equal(el('nt-tg-startup').checked,false);assert.equal(el('nt-mail-startup').checked,true);
  el('nt-tg-save').listeners.click();assert.equal(el('nt-tg-save').disabled,true);
  const post=requests.shift();assert.equal(post.opts.method,'POST');
  assert.equal(JSON.parse(post.opts.body).telegram.notify_startup,false);assert.equal(JSON.parse(post.opts.body).telegram.notify_poweron,true);assert.equal(JSON.parse(post.opts.body).email,undefined);
  input('nt-tg-token','newer-draft');assert.equal(el('nt-tg-save').disabled,true);
  el('nt-tg-save').listeners.click();assert.equal(requests.length,0,'duplicate save refused while a request is pending');
  post.resolve(response({ok:true}));await turn();requests.shift().resolve(response(body('draft-chat')));await turn();
  assert.equal(el('nt-tg-token').value,'newer-draft','newer input survives save completion');
  assert.equal(el('nt-tg-save').disabled,false);assert.equal(el('nt-mail-pass').value,'draft-password');
  assert.equal(el('nt-mail-save').disabled,false,'saving Telegram never discards email draft');
  el('nt-mail-save').listeners.click();const mailPost=requests.shift();
  assert.equal(JSON.parse(mailPost.opts.body).email.notify_startup,true);assert.equal(JSON.parse(mailPost.opts.body).telegram,undefined);
  mailPost.resolve(response({ok:true}));await turn();requests.shift().resolve(response(body()));await turn();
  load=context.ntUi.load();requests.shift().resolve(response({telegram:{},email:{}}));await load;
  assert.match(el('nt-tg-note').textContent,/Invalid notification settings response/);
  assert.equal(el('nt-tg-token').value,'newer-draft');
  input('nt-grace','180');el('nt-timing-save').listeners.click.call(el('nt-timing-save'));
  const timing=requests.shift();assert.equal(timing.url,'/api/notify');
  assert.deepEqual(JSON.parse(timing.opts.body),{connectivity_grace_seconds:180});
  input('nt-grace','240');timing.resolve(response({ok:true}));await turn();
  requests.shift().resolve(response(body()));await turn();
  assert.equal(el('nt-grace').value,'240');assert.equal(el('nt-timing-save').disabled,false);
  input('nt-grace','1.5');el('nt-timing-save').listeners.click.call(el('nt-timing-save'));assert.equal(requests.length,0);
  console.log('PASS actual notification controller: stale read rejection, poll-safe drafts, no duplicate save, in-flight edits and separate channel state');
})().catch(e=>{console.error(e);process.exitCode=1;});
