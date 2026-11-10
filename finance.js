'use strict';

const financeCloud=(()=>{
  const url="https://btgtgcwbrrnfbctchata.supabase.co";
  const publicKey="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ0Z3RnY3dicnJuZmJjdGNoYXRhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3MTQ2OTgsImV4cCI6MjA5MjI5MDY5OH0.lyEWFcmsL3GIm0FrEZdGkK2uRSx26cNiBGFvCVsjdsY";
  const sessionKey='life_os_session';
  const table='/rest/v1/finance_vaults';
  const session=()=>{
    try{return JSON.parse(localStorage.getItem(sessionKey)||'null');}
    catch{return null;}
  };
  function authError(){
    const error=new Error('Войди в тот же аккаунт «ЖИЗНЬ.exe» на этом устройстве.');
    error.code='login';
    return error;
  }
  function passwordError(status,value){
    const code=value.error_code||value.code;
    if(status===429||code==='over_request_rate_limit')return 'Слишком много попыток входа. Попробуй через несколько минут.';
    switch(code){
      case 'invalid_credentials':
        return 'Почта или пароль не подошли. Нужен пользователь, созданный для «ЖИЗНЬ.exe» в Supabase → Authentication → Users.';
      case 'email_not_confirmed':
        return 'Почта ещё не подтверждена. Открой письмо с подтверждением аккаунта «ЖИЗНЬ.exe».';
      case 'user_banned':
        return 'Вход для этого пользователя заблокирован в настройках приложения.';
      case 'email_provider_disabled':
        return 'В проекте Supabase отключён вход по почте.';
      case 'captcha_failed':
        return 'В проекте требуется проверка CAPTCHA. Эта форма входа её пока не поддерживает.';
    }
    if(status===401||status===403)return 'Сервер отклонил подключение. Проверь настройки входа в проекте Supabase.';
    if(status===404)return 'Сервис входа Supabase не найден. Проверь, что проект открыт и активен.';
    if(status>=500)return 'Сервис входа Supabase временно недоступен. Попробуй позже.';
    return 'Сервис входа отклонил запрос. Проверь настройки входа в проекте Supabase.';
  }
  async function token(grant,body){
    let response;
    try{
      response=await fetch(url+'/auth/v1/token?grant_type='+grant,{
        method:'POST',headers:{apikey:publicKey,'Content-Type':'application/json'},
        body:JSON.stringify(body),signal:AbortSignal.timeout(12000)
      });
    }catch{
      throw new Error('Нет связи с сервисом входа. Проверь интернет и попробуй ещё раз.');
    }
    const value=await response.json().catch(()=>null);
    if(!response.ok){
      if(grant==='refresh_token'&&(response.status===400||response.status===401))throw authError();
      throw new Error(passwordError(response.status,value||{}));
    }
    if(!value?.user?.id||!value.access_token)throw new Error('Сервис входа не вернул данные аккаунта. Попробуй ещё раз.');
    localStorage.setItem(sessionKey,JSON.stringify(value));
    return value;
  }
  let refreshing;
  async function request(owner,suffix,options={}){
    let current=session();
    if(!current?.access_token||current.user?.id!==owner)throw authError();
    const call=access=>fetch(url+table+suffix,{...options,signal:AbortSignal.timeout(12000),headers:{
      apikey:publicKey,Authorization:'Bearer '+access,'Content-Type':'application/json',Prefer:'return=representation'
    }});
    let result=await call(current.access_token);
    if(result.status===401){
      const newest=session();
      if(newest?.user?.id!==owner||!newest.refresh_token)throw authError();
      if(newest.access_token!==current.access_token)current=newest;
      else {
        if(!refreshing)refreshing=token('refresh_token',{refresh_token:newest.refresh_token}).finally(()=>{refreshing=null;});
        current=await refreshing;
      }
      if(current.user.id!==owner)throw authError();
      result=await call(current.access_token);
    }
    if(result.status===401)throw authError();
    if(result.status===404||result.status===403){
      const error=new Error('Синхронизация ещё не настроена в Supabase.');
      error.code='setup';
      throw error;
    }
    if(result.status===409){
      const error=new Error('Общие данные изменились на другом устройстве. Обнови их и повтори действие.');
      error.code='conflict';
      throw error;
    }
    if(!result.ok)throw new Error('Не удалось связаться с общим бюджетом. Проверь соединение.');
    return result.json();
  }
  async function read(owner){
    const rows=await request(owner,'?select=vault&user_id=eq.'+encodeURIComponent(owner));
    return rows[0]?.vault||null;
  }
  async function write(owner,vault,previous){
    const filter='?user_id=eq.'+encodeURIComponent(owner)+'&revision=eq.'+encodeURIComponent(previous);
    const row={revision:vault.revision,vault};
    const result=previous?await request(owner,filter,{method:'PATCH',body:JSON.stringify(row)}):
      await request(owner,'',{method:'POST',body:JSON.stringify({...row,user_id:owner})});
    if(result.length!==1){
      const error=new Error('Общие данные изменились на другом устройстве. Обнови их и повтори действие.');
      error.code='conflict';
      throw error;
    }
  }
  async function recoveryRequest(endpoint,method,body,access){
    let response;
    try{
      response=await fetch(url+'/auth/v1/'+endpoint,{
        method,headers:{apikey:publicKey,'Content-Type':'application/json',...(access?{Authorization:'Bearer '+access}:{})},
        body:JSON.stringify(body),signal:AbortSignal.timeout(12000)
      });
    }catch{
      throw new Error('Нет связи с сервисом входа. Попробуй ещё раз.');
    }
    if(response.ok)return;
    const value=await response.json().catch(()=>({}));
    if(response.status===429)throw new Error('Слишком много попыток. Попробуй через несколько минут.');
    if(access&&(response.status===401||['bad_jwt','otp_expired','session_not_found','session_expired'].includes(value?.code||value?.error_code))){
      throw new Error('Ссылка больше не действует. Запроси новое письмо.');
    }
    if(access&&(value?.code==='weak_password'||value?.error_code==='weak_password')){
      throw new Error('Выбери более сложный пароль.');
    }
    if(access&&(value?.code==='same_password'||value?.error_code==='same_password')){
      throw new Error('Новый пароль должен отличаться от прежнего.');
    }
    throw new Error(access?'Не удалось изменить пароль. Попробуй ещё раз.':'Не удалось отправить письмо. Попробуй ещё раз.');
  }
  return {session,sessionKey,read,write,login:(email,password)=>token('password',{email,password}),
    recover:(email,redirect)=>recoveryRequest('recover?redirect_to='+encodeURIComponent(redirect),'POST',{email}),
    setPassword:(access,password)=>recoveryRequest('user','PUT',{password},access)};

})();

const $ = id => document.getElementById(id);
const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Kyiv'}).format(new Date());
const isoMonth = date => date.slice(0,7);
const monthName = month => new Intl.DateTimeFormat('ru-RU',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(month+'-01')).replace(/ г\.$/,'');
const shortDate = date => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',timeZone:'UTC'}).format(new Date(date));
const monthEnd = month => new Date(Date.UTC(Number(month.slice(0,4)),Number(month.slice(5,7)),0)).toISOString().slice(0,10);
const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value||'')&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,10)===value;
const monthRange = month => ({start:month+'-01',end:month===isoMonth(today())?today():monthEnd(month),label:monthName(month)});
const money = cents => new Intl.NumberFormat('uk-UA',{minimumFractionDigits:cents%100?2:0,maximumFractionDigits:2}).format(cents/100)+' грн';
const inputMoney = cents => cents==null?'':(cents/100).toFixed(2);
const signed = cents => (cents>0?'+':cents<0?'−':'')+money(Math.abs(cents));
const n = (tag, text='', cls='') => {
  const el=document.createElement(tag);
  el.textContent=text;
  if(cls)el.className=cls;
  return el;
};
const button = (text, click, cls='') => {
  const el=n('button',text,cls);
  el.type='button';
  el.addEventListener('click',click);
  return el;
};
const option = (value,text) => new Option(text,value);
const labels={expense:'Расход',income:'Доход',internal:'Перемещение'};
const methods={card:'Карта',cash:'Наличные'};
const baseCategories={
  unknown:'Не определено',groceries:'Продукты',food:'Кафе и доставка готовой еды',taxi:'Такси',
  transit:'Транспорт',clothes:'Одежда и обувь',home:'Товары для дома',education:'Образование и занятия',
  toys:'Игрушки и развлечения',health:'Здоровье',pets:'Животные',digital:'Цифровые сервисы',
  games:'Игры',shopping:'Интернет-покупки',bank:'Банковские услуги',rent:'Аренда',
  utility:'Коммунальные услуги',stationery:'Книги и канцтовары',beauty:'Красота',mobile:'Мобильная связь',tobacco:'Сигареты',transfers:'Переводы без назначения',other:'Прочее'
};
const knownMerchants=[
  [/сільпо|сильпо|silpo/,'Сільпо','groceries'],[/glovo|глово/,'Glovo','food'],
  [/uklon|уклон/,'Uklon','taxi'],[/steam/,'Steam','games'],[/temu/,'Temu','shopping'],
  [/rozetka|розетк/,'Rozetka','shopping'],[/sinsay/,'Sinsay','clothes']
];
const blank = () => ({version:1,operations:[],deleted:[],categories:{...baseCategories},rules:{},obligations:[],
  subscriptions:[],dismissed:[],open:{},lastImport:null});
const normalize = financeExcel.words;
const uuid = () => crypto.randomUUID();
const utf8 = new TextEncoder();
const decoder = new TextDecoder();
const bytes = length => crypto.getRandomValues(new Uint8Array(length));
const encode64 = value => {
  let str='';
  for(let i=0;i<value.length;i+=8192)str+=String.fromCharCode(...value.subarray(i,i+8192));
  return btoa(str);
};
const decode64 = value => Uint8Array.from(atob(value),c=>c.charCodeAt(0));
const digest = async value => encode64(new Uint8Array(await crypto.subtle.digest('SHA-256',utf8.encode(value))));
const issue = (message='') => {
  $('status').textContent=message;
  $('status').hidden=!message;
};
let db, record, key, state, busy=false, view='gate';
let cloudOwner=null, cloudSeed=null;
const fopLocalKey='life-os-fop-2026-v1', sharedOwnerKey='life-os-finance-shared-owner';
function knownCloud(owner){
  try{return Boolean(owner)&&localStorage.getItem(sharedOwnerKey)===owner;}
  catch{return false;}
}
function rememberCloud(owner){
  try{localStorage.setItem(sharedOwnerKey,owner);}catch{}
}
let range=monthRange(isoMonth(today())), compare=null, historyMerchant='', categoryLila=false, analyticsLila=false;
let historyLimit=100, cardSelection=null;
const sections=['gate','finance-home','budget','fop','analytics','review','subscriptions'];
let wantedFop=location.hash==='#fop';

function openDatabase(){
  return new Promise((resolve,reject)=>{
    const req=indexedDB.open('life-os-finance',1);
    req.onupgradeneeded=()=>req.result.createObjectStore('vault');
    req.onsuccess=()=>resolve(req.result);
    req.onerror=()=>reject(req.error);
    req.onblocked=()=>reject(new Error('Закрой другую вкладку «Финансов» и обнови страницу.'));
  });
}
function readLocalVault(){
  return new Promise((resolve,reject)=>{
    const req=db.transaction('vault').objectStore('vault').get('budget');
    req.onsuccess=()=>resolve(req.result||null);
    req.onerror=()=>reject(req.error);
  });
}
function writeLocalVault(next,expected){
  return new Promise((resolve,reject)=>{
    const tx=db.transaction('vault','readwrite'), store=tx.objectStore('vault');
    let conflict=false;
    const current=store.get('budget');
    current.onsuccess=()=>{
      if((current.result?.revision||null)!==expected){conflict=true;tx.abort();return;}
      store.put(next,'budget');
    };
    tx.oncomplete=()=>resolve();
    tx.onabort=()=>reject(conflict?new Error('Данные изменились в другой вкладке. Войди заново, чтобы продолжить.'):tx.error);
  });
}
function readVault(){
  return cloudOwner?financeCloud.read(cloudOwner):readLocalVault();
}
function writeVault(next,expected){
  return cloudOwner?financeCloud.write(cloudOwner,next,expected):writeLocalVault(next,expected);
}
function legacyFop(){
  const value=JSON.parse(localStorage.getItem(fopLocalKey)||'null');
  if(value&&(!Array.isArray(value.receipts)||!value.paid))throw new Error('Локальные записи ФОП не удалось прочитать.');
  return value;
}
async function selectCloud(owner,{automatic=false}={}){
  const shared=await financeCloud.read(owner);
  if(automatic&&!shared)return false;
  if(financeCloud.session()?.user?.id!==owner)throw new Error('Аккаунт изменился. Войди заново.');
  const local=shared?null:await readLocalVault();
  cloudOwner=owner;cloudSeed=local;record=shared;
  if(shared)rememberCloud(owner);
  showGate();
  issue(shared?'':'Общая копия ещё не создана. Заверши настройку на устройстве, где есть актуальные записи.');
  return true;
}
async function refreshCloud({manual=false}={}){
  if(!cloudOwner||!key)return;
  const secret=key, owner=cloudOwner;
  await saveQueue;
  if(key!==secret||cloudOwner!==owner)return;
  const previous=record.revision;
  try{
    const shared=await financeCloud.read(owner);
    if(key!==secret||record.revision!==previous)return;
    if(!shared)throw new Error('Общая копия пока недоступна.');
    if(shared.revision!==previous){
      const latest=await decrypt(shared,secret);
      if(key!==secret||record.revision!==previous)return;
      record=shared;state=latest;
      render();
      if(view==='fop'&&manual)$('fop-frame').contentWindow.financeFopRefresh?.();
    }
    if(manual)issue('Общие данные актуальны.');
  }catch(error){
    if(key!==secret||record.revision!==previous)return;
    if(error.name==='OperationError'||error.code==='login'){
      record=null;cloudSeed=null;showGate();
      issue('Войди заново, чтобы открыть общие записи.');
    }else if(manual)issue(error.message||'Не удалось обновить общие записи.');
  }
}
async function derive(pin,salt){
  const base=await crypto.subtle.importKey('raw',utf8.encode(pin),'PBKDF2',false,['deriveKey']);
  return crypto.subtle.deriveKey({name:'PBKDF2',salt,iterations:600000,hash:'SHA-256'},base,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
}
async function decrypt(vault,secret){
  const data=await crypto.subtle.decrypt({name:'AES-GCM',iv:decode64(vault.iv)},secret,decode64(vault.data));
  const value=JSON.parse(decoder.decode(data));
  if(value.version!==1||!Array.isArray(value.operations)||!Array.isArray(value.deleted)||!value.categories?.unknown||
    !Array.isArray(value.obligations)||!Array.isArray(value.subscriptions)||!Array.isArray(value.dismissed)||!value.rules||!value.open){
    throw new Error('Неизвестный формат бюджета.');
  }
  return updateImported(value);
}
async function encrypt(value,secret,salt){
  const iv=bytes(12);
  const data=await crypto.subtle.encrypt({name:'AES-GCM',iv},secret,utf8.encode(JSON.stringify(value)));
  return {version:1,revision:uuid(),salt:encode64(salt),iv:encode64(iv),data:encode64(new Uint8Array(data))};
}
let saveQueue=Promise.resolve();
function commit(change){
  const secret=key;
  if(!secret||busy)return Promise.resolve(false);
  const save=async()=>{
    if(key!==secret)return false;
    try{
      const next=structuredClone(state);
      change(next);
      updateImported(next);
      const encrypted=await encrypt(next,secret,decode64(record.salt));
      if(key!==secret)return false;
      await writeVault(encrypted,record.revision);
      record=encrypted;
      if(key!==secret)return false;
      state=next;
      issue();
      render();
      return true;
    }catch(error){
      issue(error?.message||'Не удалось сохранить данные.');
      return false;
    }
  };
  const result=saveQueue.then(save);
  saveQueue=result.catch(()=>{});
  return result;
}
function showGate(){
  key=null;state=null;
  for(const id of ['home-summary','summary','category-list','history-list','obligation-list','review-list','analytics-content','comparison','subscription-list']){
    $(id).replaceChildren();
  }
  document.querySelector('.print-report')?.remove();
  closeSheet();
  openView('gate');
  const connecting=Boolean(cloudOwner&&!record&&!knownCloud(cloudOwner));
  $('cloud-mode').textContent=connecting?'Подключение к общим «Финансам»':
    cloudOwner?'Общие «Финансы» · один PIN для телефона и ПК':'Локальные «Финансы» · только на этом устройстве';
  $('cloud-connect').hidden=Boolean(cloudOwner);
  $('cloud-local').hidden=!cloudOwner;
  const hasPin=Boolean(record||cloudSeed||knownCloud(cloudOwner));
  $('gate-title').textContent=hasPin?'Вход по PIN':'Создай PIN';
  $('gate-note').textContent=cloudSeed?'Введи PIN этого устройства и нажми «Завершить синхронизацию». Его записи и PIN станут общими.':
    hasPin?'':'От 6 до 12 цифр. Этот PIN также понадобится для восстановления из копии.';
  $('unlock').querySelector('button').textContent=connecting?'Завершить синхронизацию':'Открыть';
  $('pin-again').hidden=hasPin;
  $('unlock').reset();
}
function openView(next){
  if(next!=='gate'&&!key)return;
  if(view==='fop'&&next!=='fop')$('fop-frame').removeAttribute('src');
  sections.forEach(id=>$(id).hidden=id!==next);
  view=next;
  $('up').hidden=['gate','finance-home'].includes(next);
  $('up').textContent=['budget','fop'].includes(next)?'← Финансы':'← Личный бюджет';
  $('exit').hidden=!['gate','finance-home'].includes(next);
  $('lock').hidden=next==='gate';
  $('cloud-refresh').hidden=!cloudOwner||next==='gate';
  if(next==='finance-home'){
    const account=cloudOwner?financeCloud.session()?.user?.email:'';
    $('finance-sync-state').textContent=cloudOwner?'Общие «Финансы»'+(account?' · '+account:''):'Локальная копия · только этот браузер';
    $('finance-sync-actions').hidden=Boolean(cloudOwner);
  }
  if(next==='fop'){
    const launch=()=>{if(view==='fop'&&key)$('fop-frame').src='fop.html?v=20261110-2';};
    if(cloudOwner)refreshCloud().then(launch);
    else launch();
  }
  window.scrollTo(0,0);
  if(state)render();
}
window.financeFopAllowed=()=>Boolean(key)&&view==='fop';
window.financeFopBack=()=>openView('finance-home');
window.financeFopRead=()=>cloudOwner&&window.financeFopAllowed()?structuredClone(state.fop??null):undefined;
window.financeFopWrite=next=>cloudOwner&&window.financeFopAllowed()?commit(value=>{value.fop=next;}):Promise.resolve(false);

$('unlock').addEventListener('submit',async event=>{
  event.preventDefault();
  if(busy)return;
  const form=event.currentTarget, values=new FormData(form), pin=String(values.get('pin'));
  if(!/^[0-9]{6,12}$/.test(pin))return;
  if(!record&&!cloudSeed&&!knownCloud(cloudOwner)&&values.get('again')!==pin){issue('PIN-коды должны совпадать.');return;}
  busy=true;
  form.querySelector('button').disabled=true;
  try{
    record=await readVault();
    const initial=record||cloudSeed;
    if(!initial&&knownCloud(cloudOwner))throw new Error('Общие записи пока недоступны. Попробуй обновить страницу.');
    const salt=initial?decode64(initial.salt):bytes(16);
    const secret=await derive(pin,salt);
    const loaded=initial?await decrypt(initial,secret):blank();
    const connectedNow=Boolean(cloudOwner&&!record);
    if(!record){
      if(cloudOwner)loaded.fop=legacyFop();
      const encrypted=await encrypt(loaded,secret,salt);
      await writeVault(encrypted,null);
      record=encrypted;cloudSeed=null;
      if(cloudOwner)rememberCloud(cloudOwner);
      else navigator.storage?.persist?.().catch(()=>{});
    }
    key=secret;state=loaded;
    range=monthRange(isoMonth(today()));compare=null;historyMerchant='';categoryLila=false;analyticsLila=false;
    $('search').value='';$('history-category').value='';$('history-type').value='';$('history-lila').checked=false;cardSelection=null;
    for(const id of ['obligations','categories','history'])$(id).open=Boolean(state.open[id]);
    issue(connectedNow?'Синхронизация завершена. На втором устройстве войди в тот же аккаунт и введи общий PIN.':'');
    openView(wantedFop?'fop':'finance-home');
    if(wantedFop)history.replaceState(null,'',location.pathname+location.search);
    wantedFop=false;
  }catch(error){
    if(error.code==='login'){cloudOwner=null;cloudSeed=null;record=await readLocalVault();showGate();}
    issue(error.name==='OperationError'?'PIN не подошёл.':error.message||'Не удалось открыть бюджет.');
  }finally{
    form.reset();busy=false;form.querySelector('button').disabled=false;
  }
});
$('exit').addEventListener('click',showGate);
$('lock').addEventListener('click',()=>{issue();showGate();});
$('cloud-refresh').addEventListener('click',()=>refreshCloud({manual:true}));
window.addEventListener('focus',()=>{if(view!=='fop')refreshCloud();});
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden&&view!=='fop')refreshCloud();
});
window.addEventListener('storage',event=>{
  if(event.key===financeCloud.sessionKey&&cloudOwner&&financeCloud.session()?.user?.id!==cloudOwner){
    key=null;
    cloudOwner=null;cloudSeed=null;record=null;showGate();
    readLocalVault().then(local=>{if(!cloudOwner&&!key){record=local;showGate();}}).catch(()=>{});
    issue('Вход в общий аккаунт завершён.');
  }
});
$('up').addEventListener('click',()=>openView(['budget','fop'].includes(view)?'finance-home':'budget'));
window.addEventListener('pagehide',()=>{
  if(key)showGate();
});
document.querySelectorAll('[data-view]').forEach(el=>el.addEventListener('click',()=>openView(el.dataset.view)));

function inRange(row,period=range){return row.date>=period.start&&row.date<=period.end;}
function operations(period=range,lila=false,applyCardFilter=true){
  return [...state.operations,...transferFees(state.operations)].filter(row=>!row.pending&&inRange(row,period)&&
    (!lila||row.type==='expense'&&row.lila)&&(!applyCardFilter||!cardSelection||!row.cardTail||cardSelection.has(row.cardTail)));
}
function transferFees(rows){
  const receipts=new Map();
  const incoming=/^з[іi] сво[єе][їіi] картки \*?(\d{4})$/;
  const outgoing=/^на свою картку \*?(\d{4})$/;
  const timestamp=row=>Date.parse(row.date+'T'+row.time+'Z');
  for(const row of rows){
    const from=normalize(row.original).match(incoming)?.[1];
    if(row.pending||row.type!=='internal'||!from||!row.cardTail||!row.time)continue;
    const key=[row.date,from,row.cardTail].join(':');
    const group=receipts.get(key)||[];
    group.push(row);receipts.set(key,group);
  }
  const result=[];
  for(const row of rows){
    const to=normalize(row.original).match(outgoing)?.[1];
    if(row.pending||row.type!=='internal'||!to||!row.cardTail||!row.time)continue;
    const pair=(receipts.get([row.date,row.cardTail,to].join(':'))||[]).filter(other=>
      Math.abs(timestamp(row)-timestamp(other))<=120000&&other.amount<=row.amount&&
      (other.transactionAmount==null||Math.abs(other.transactionAmount)===row.amount));
    if(pair.length===1&&row.amount>pair[0].amount){
      result.push({...row,id:row.id+'-fee',feeSource:row.id,type:'expense',category:'bank',merchant:'Комиссия за перевод',
        amount:row.amount-pair[0].amount,lila:false});
    }
  }
  return result;
}
function totals(rows,period){
  let income=0,expense=0,fop=0;
  for(const row of rows){
    if(row.type==='income'){
      income+=row.amount;
      if(row.fopFunding)fop+=row.amount;
    }
    if(row.type==='expense')expense+=row.amount;
  }
  const days=Math.max(1,Math.round((Date.parse(period.end)-Date.parse(period.start))/86400000)+1);
  return {income,expense,fop,difference:income-expense,average:Math.round(expense/days)};
}
function metric(label,value,cls=''){
  const row=n('div','','metric '+cls);
  row.append(n('span',label),n('b',value));return row;
}
function stats(summary,interactive=false){
  const flow=(label,value,type)=>interactive?rowButton(label,'',money(value),()=>drill('','',false,type)):metric(label,money(value));
  return [flow('Поступило в бюджет',summary.income,'income'),
    ...(summary.fop?[flow('В том числе с ФОП',summary.fop,'fop')]:[]),
    flow('Потрачено',summary.expense,'expense'),
    metric('Разница за период',signed(summary.difference),'total'),metric('Средний расход за день',money(summary.average))];
}
function categoryName(id){return state.categories[id]||state.categories.unknown;}
function rowButton(title,sub,value,click){
  const el=button('',click,'list-row');
  const text=n('span');text.append(n('strong',title));
  if(sub)text.append(n('small',sub));
  el.append(text,n('strong',value));
  return el;
}
const empty = message => n('p',message,'muted');
function categoryOptions(select,all=false){
  const old=select.value;
  select.replaceChildren(...(all?[option('','Все категории')]:[]),
    ...Object.entries(state.categories).map(([id,label])=>option(id,label)));
  select.value=Object.hasOwn(state.categories,old)?old:all?'':'unknown';
}
function group(rows,getKey){
  const groups=new Map();
  for(const row of rows){
    if(row.type!=='expense')continue;
    const k=getKey(row);
    const value=groups.get(k)||{amount:0,count:0};
    value.amount+=row.amount;value.count++;
    groups.set(k,value);
  }
  return [...groups].sort((a,b)=>b[1].amount-a[1].amount);
}
function matchesHistory(row){
  const category=$('history-category').value, type=$('history-type').value, search=normalize($('search').value);
  const strings=[row.merchant,row.original,row.note,categoryName(row.category),money(row.amount),inputMoney(row.amount)];
  const matchesType=type==='fop'?row.type==='income'&&row.fopFunding:!type||row.type===type;
  return matchesType&&(!category||row.type==='expense'&&row.category===category)&&
    (!$('history-lila').checked||row.type==='expense'&&row.lila)&&
    (!historyMerchant||normalize(row.merchant)===(historyMerchant===':empty:'?'':historyMerchant))&&
    (!search||strings.some(value=>normalize(value).includes(search))||
      (financeExcel.number(search)!==null&&Math.abs(financeExcel.number(search))===row.amount));
}
const operationTypeLabel=row=>row.type==='income'&&row.fopFunding?'Пополнение с ФОП':labels[row.type];
function operationRow(row){
  const amount=row.type==='internal'?money(row.amount):signed(row.type==='expense'?-row.amount:row.amount);
  const sub=[row.type==='expense'?categoryName(row.category):operationTypeLabel(row),row.type==='expense'&&row.lila?'Лила':'',
    row.cardTail?'Карта •'+row.cardTail:methods[row.method]].filter(Boolean).join(' · ');
  return rowButton(row.merchant||labels[row.type],sub,amount,()=>{
    if(row.feeSource){
      const transfer=state.operations.find(item=>item.id===row.feeSource);
      if(transfer)operationSheet(transfer);
    }else operationSheet(row);
  });
}
function renderHistory(){
  const rows=operations().filter(matchesHistory).sort((a,b)=>b.date.localeCompare(a.date)||String(b.time||'').localeCompare(a.time||''));
  $('history-summary').textContent=operations().length+' операций за период';
  $('history-merchant').hidden=!historyMerchant;
  $('history-merchant').replaceChildren(...(historyMerchant?[button((historyMerchant===':empty:'?'Без получателя':historyMerchant)+' ×',()=>{historyMerchant='';renderHistory();})]:[]));
  const display=[];
  let date='';
  for(const row of rows.slice(0,historyLimit)){
    if(date!==row.date){date=row.date;display.push(n('h3',shortDate(date),'date-group'));}
    display.push(operationRow(row));
  }
  if(rows.length>historyLimit)display.push(button('Показать ещё',()=>{historyLimit+=100;renderHistory();}));
  if(!rows.length&&['rent','utility'].includes($('history-category').value)&&
    ![...housingRules(state.obligations).values()].some(rule=>rule.utility&&rule.rents.size)){
    display.push(empty('Чтобы распределять переводы арендодателю, загрузи личные шаблоны обязательств или укажи одного получателя в аренде и коммуналке.'));
    display.push(button('Открыть обязательные платежи',()=>{
      $('obligations').open=true;
      $('bill-presets').scrollIntoView({block:'center'});
    }));
  }
  $('history-list').replaceChildren(...(display.length?display:[empty('Операций по этим фильтрам нет.')]));

}
function drill(category,merchant='',lila=false,type=''){
  openView('budget');
  $('history-category').value=category;
  $('history-type').value=type;
  $('history-lila').checked=lila;
  $('search').value='';
  historyMerchant=merchant;historyLimit=100;
  $('history').open=true;
  renderHistory();
  $('history').scrollIntoView();
}
function render(){
  if(!state)return;
  const current=monthRange(isoMonth(today())), now=totals(operations(current,false,false),current);
  $('home-month').textContent=current.label;
  $('home-summary').replaceChildren(metric('Поступило в бюджет',money(now.income)),
    ...(now.fop?[metric('В том числе с ФОП',money(now.fop))]:[]),metric('Потрачено',money(now.expense)),
    metric('Разница за месяц',signed(now.difference),'total'));
  if(view==='budget'){
    $('period-button').textContent=range.label+' ⌄';
    $('period-note').textContent=shortDate(range.start)+' — '+shortDate(range.end);
    const cards=[...new Set(state.operations.map(row=>row.cardTail).filter(Boolean))];
    $('cards-filter').hidden=cards.length<2;
    $('cards-filter').textContent=cardSelection?'Карты '+[...cardSelection].map(card=>'•'+card).join(', ')+' ⌄':'Все карты ⌄';
    $('summary').replaceChildren(...stats(totals(operations(),range),true));
    categoryOptions($('history-category'),true);
    renderHistory();
    const breakdown=group(operations(range,categoryLila),row=>row.category);
    $('category-filter').setAttribute('aria-pressed',String(categoryLila));
    $('category-filter').classList.toggle('lilac',categoryLila);
    $('category-summary').textContent=breakdown.slice(0,3).map(([id])=>categoryName(id)).join(' · ')||'Нет расходов за период';
    $('category-list').replaceChildren(...breakdown.map(([id,value])=>rowButton(categoryName(id),'',money(value.amount),()=>drill(id,'',categoryLila))));
    renderObligations();
  }
  if(view==='analytics')renderAnalytics();
  if(view==='review')renderReview();
  if(view==='subscriptions')renderSubscriptions();
}
for(const id of ['history-category','history-type','history-lila','search'])$(id).addEventListener('input',()=>{historyLimit=100;renderHistory();});
$('category-filter').addEventListener('click',()=>{categoryLila=!categoryLila;render();});
for(const id of ['obligations','categories','history']){
  $(id).addEventListener('toggle',()=>{
    if(state&&view==='budget'&&Boolean(state.open[id])!==$(id).open){
      commit(next=>{next.open[id]=$(id).open;});
    }
  });
}
const dialog=$('sheet');
function sheet(content){
  const close=button('×',closeSheet,'sheet-close');
  close.setAttribute('aria-label','Закрыть');
  const handle=n('div','','handle');
  let start=null;
  handle.addEventListener('pointerdown',event=>{start=event.clientY;handle.setPointerCapture(event.pointerId);});
  handle.addEventListener('pointerup',event=>{if(start!==null&&event.clientY-start>35)closeSheet();start=null;});
  $('sheet-body').replaceChildren(handle,close,...content);
  if(!dialog.open)dialog.showModal();
}
function closeSheet(){
  if(dialog.open)dialog.close();
  $('sheet-body').replaceChildren();
}
dialog.addEventListener('click',event=>{if(event.target===dialog)closeSheet();});
dialog.addEventListener('close',()=>{if(!dialog.open)$('sheet-body').replaceChildren();});
function sheetForm(markup){
  const form=n('form');
  form.innerHTML=markup;
  sheet([form]);
  return form;
}
const field = (form,name) => form.elements.namedItem(name);
const formData = form => Object.fromEntries(new FormData(form).entries());
const formIssue = (form,message) => {form.querySelector('[role="status"]').textContent=message;};
function chooser(initial,caption,onChange){
  const form=sheetForm('<h2>Период</h2><label>Выбор<select name="mode"><option value="month">Месяц</option><option value="year">Год</option><option value="custom">Диапазон дат</option></select></label><label data-mode="month">Месяц<input name="month" type="month"></label><label data-mode="year" hidden>Год<input name="year" type="number" min="1900" max="9999"></label><div class="grid" data-mode="custom" hidden><label>С<input name="start" type="date"></label><label>По<input name="end" type="date"></label></div><p role="status"></p><div class="actions"><button class="lilac">Применить</button><button type="button" name="current">Текущий месяц</button></div>');
  const mode=field(form,'mode');
  mode.value=initial.mode||'month';
  field(form,'month').value=isoMonth(initial.start);
  field(form,'year').value=initial.start.slice(0,4);
  field(form,'start').value=initial.start;
  field(form,'end').value=initial.end;
  form.querySelector('h2').textContent=caption;
  const display=()=>form.querySelectorAll('[data-mode]').forEach(el=>{el.hidden=el.dataset.mode!==mode.value;});
  mode.addEventListener('change',display);
  display();
  const choose=period=>{onChange(period);closeSheet();render();};
  field(form,'current').addEventListener('click',()=>choose(monthRange(isoMonth(today()))));
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const data=formData(form);
    let selected;
    if(data.mode==='month'&&validDate(data.month+'-01'))selected=monthRange(data.month);
    if(data.mode==='year'&&validDate(data.year+'-01-01'))selected={start:data.year+'-01-01',end:data.year+'-12-31',label:data.year,mode:'year'};
    if(data.mode==='custom'&&validDate(data.start)&&validDate(data.end))selected={start:data.start,end:data.end,label:'Свой период',mode:'custom'};
    if(!selected||selected.start>selected.end||selected.start>today()){formIssue(form,'Проверь даты периода.');return;}
    if(selected.end>today())selected.end=today();
    choose(selected);
  });
}
const chooseRange=()=>chooser(range,'Выбрать период',value=>{range=value;historyLimit=100;});
$('period-button').addEventListener('click',chooseRange);
$('cards-filter').addEventListener('click',()=>{
  const cards=[...new Set(state.operations.map(row=>row.cardTail).filter(Boolean))].sort();
  const form=sheetForm('<h2>Карты в сводке</h2><p class="muted">Ручные записи без привязки к карте остаются в сводке.</p><div id="card-options"></div><p role="status"></p><button class="lilac">Применить</button>');
  for(const card of cards){
    const label=n('label','','check'), input=n('input');
    input.type='checkbox';input.name='card';input.value=card;
    input.checked=!cardSelection||cardSelection.has(card);
    label.append(input,n('span','Карта •'+card));$('card-options').append(label);
  }
  form.addEventListener('submit',event=>{
    event.preventDefault();
    const selected=new FormData(form).getAll('card');
    if(!selected.length){formIssue(form,'Выбери хотя бы одну карту.');return;}
    cardSelection=selected.length===cards.length?null:new Set(selected);
    historyLimit=100;
    closeSheet();render();
  });
});
$('analytics-period').addEventListener('click',chooseRange);
$('compare-button').addEventListener('click',()=>{
  const previous=new Date(range.start);previous.setUTCDate(0);
  chooser(compare||monthRange(isoMonth(previous.toISOString())),'Период для сравнения',value=>{compare=value;});
});
async function connectCloud(){
  if(busy||key)return;
  const owner=financeCloud.session()?.user?.id;
  if(owner){
    busy=true;
    try{await selectCloud(owner);}
    catch(error){
      if(error.code==='login')cloudLogin();
      else issue(error.message||'Синхронизация недоступна.');
    }finally{busy=false;}
  }else cloudLogin();
}
$('cloud-connect').addEventListener('click',connectCloud);
$('cloud-connect-home').addEventListener('click',async()=>{
  await saveQueue;
  if(busy||!key||cloudOwner)return;
  showGate();
  await connectCloud();
});
$('cloud-local').addEventListener('click',async()=>{
  if(busy||key)return;
  busy=true;
  const unlock=$('unlock').querySelector('button');
  unlock.disabled=true;
  try{
    const local=await readLocalVault();
    cloudOwner=null;cloudSeed=null;record=local;showGate();
    issue('Открыта локальная копия на этом устройстве.');
  }catch(error){issue(error.message||'Локальная копия недоступна.');}
  finally{unlock.disabled=false;busy=false;}
});
function recoveryEmail(email=''){
  const form=sheetForm('<h2>Восстановить пароль</h2><label>Почта пользователя «ЖИЗНЬ.exe»<input name="email" type="email" autocomplete="username" required></label><p role="status"></p><button class="lilac">Отправить письмо</button>');
  field(form,'email').value=email;
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const submit=form.querySelector('button');
    if(submit.disabled)return;
    submit.disabled=true;
    formIssue(form,'');
    try{
      const redirect=new URL('finance.html',location.href).href;
      await financeCloud.recover(field(form,'email').value.trim(),redirect);
      formIssue(form,'Если такой аккаунт есть, на эту почту придёт новая ссылка.');
    }catch(error){formIssue(form,error.message);}
    finally{submit.disabled=false;}
  });
}
function chooseNewPassword(access){
  const form=sheetForm('<h2>Новый пароль</h2><p class="muted">Этот пароль нужен для входа в аккаунт «ЖИЗНЬ.exe». PIN для финансов вводится отдельно.</p><label>Новый пароль<input name="password" type="password" autocomplete="new-password" minlength="8" required></label><label>Повтори пароль<input name="repeat" type="password" autocomplete="new-password" minlength="8" required></label><p role="status"></p><div class="actions"><button class="lilac">Сохранить пароль</button><button type="button" name="retry">Запросить новую ссылку</button></div>');
  field(form,'retry').addEventListener('click',()=>{access=null;recoveryEmail();});
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const submit=form.querySelector('button');
    if(submit.disabled||!access)return;
    const password=field(form,'password').value;
    if(password!==field(form,'repeat').value){formIssue(form,'Пароли должны совпадать.');return;}
    submit.disabled=true;
    formIssue(form,'');
    try{
      await financeCloud.setPassword(access,password);
      access=null;
      form.reset();
      cloudLogin();
      formIssue($('sheet-body').querySelector('form'),'Пароль обновлён. Войди с новым паролем.');
    }catch(error){formIssue(form,error.message);}
    finally{submit.disabled=false;}
  });
}
function showRecoveryCallback(){
  const callback=window.takeFinanceRecovery?.();
  if(!callback?.token&&!callback?.error)return false;
  showGate();
  if(callback.token)chooseNewPassword(callback.token);
  else{
    recoveryEmail();
    formIssue($('sheet-body').querySelector('form'),'Ссылка больше не действует. Запроси новое письмо.');
  }
  return true;
}
window.addEventListener('finance-recovery',()=>{if(db)showRecoveryCallback();});
function cloudLogin(){
  const form=sheetForm('<h2>Общие финансы</h2><p class="muted">На обоих устройствах используй почту и пароль пользователя «ЖИЗНЬ.exe» из проекта Supabase. PIN понадобится после входа.</p><label>Почта<input name="email" type="email" autocomplete="username" required></label><label>Пароль<input name="password" type="password" autocomplete="current-password" required></label><p role="status"></p><div class="actions"><button class="lilac">Войти</button><button type="button" name="recover">Забыли пароль?</button></div>');
  field(form,'recover').addEventListener('click',()=>recoveryEmail(field(form,'email').value.trim()));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(busy)return;
    busy=true;form.querySelector('button').disabled=true;
    try{
      const result=await financeCloud.login(field(form,'email').value.trim(),field(form,'password').value);
      await selectCloud(result.user.id);
    }catch(error){
      formIssue(form,error.message||'Не удалось войти.');
    }finally{
      busy=false;field(form,'password').value='';form.querySelector('button').disabled=false;
    }
  });
}
$('plus').addEventListener('click',()=>{
  const actions=n('div','','sheet-menu');
  actions.append(button('Добавить операцию',()=>operationSheet(),'yellow'),button('Импортировать выписку',importSheet));
  sheet([n('h2','Добавить'),actions]);
});
function ruleKey(merchant){return normalize(merchant);}
function merchantRule(rules,key){return Object.hasOwn(rules,key)?rules[key]:null;}
const mixedMerchant=name=>/sinsay|temu|rozetka|розетк/.test(normalize(name));
const descriptionCategories=[
  [/аптек|apteka|citimed/,'health'],[/тавр[іи]я|frukty i ovo|магазин[- ]кафетер[іiи]й коло|^коло(?:\s|$)/,'groceries'],
  [/^(?:кафе|kafe)|coffeeroom|dominos/,'food'],[/adobe|apple/,'digital'],[/blizzard/,'games'],
  [/(?:к[іiи]оск|kiosk)\s+(?:105|124)(?:\b|$)/,'tobacco'],
  [/zoomahazyn|torzoo/,'pets'],[/railway|міський транспорт/,'transit'],
  [/vodafone/,'mobile'],[/^(?:за обслуговування картки|комісія|комиссия|bank fee)/,'bank']
];
const bankCategories={
  'аптеки':'health','книги та канцтовари':'stationery','ресторани, кафе, бари':'food',
  'таксі':'taxi','супермаркети та продукти':'groceries','цифрові товари':'digital',
  'розваги':'toys','тварини':'pets','інтернет-магазини':'shopping','транспорт':'transit',
  'дім та ремонт':'home','краса':'beauty','комуналка та інтернет':'utility','поповнення мобільного':'mobile'
};
function merchantInfo(original,merchant,bankCategory){
  const name=merchant||original, text=normalize(name+' '+original);
  const known=knownMerchants.find(([pattern])=>pattern.test(text));
  const category=descriptionCategories.find(([pattern])=>pattern.test(text))?.[1];
  return {name:known?.[1]||name,category:known?.[2]||category||bankCategories[normalize(bankCategory)]||'unknown'};
}
function fopTransfer(original){
  const text=normalize(original);
  return /(?:^|[^\p{L}])(?:фоп|fop)(?=$|[^\p{L}])/u.test(text)&&
    /переказ власних кошт[іi]в|переказ частини власного прибутку|perekaz chastyny vlasnoho prybutku/.test(text);
}
function ownTransfer(original){
  return /скарбнич|копилк|між власними|між своїми|между своими|между собственными|обмін валют|обмен валют|з[іi] сво[єе][їіi] картки|на свою картку|переказ власних кошт[іi]в|\bfop\b.*perekaz chastyny vlasnoho prybutku|^(?:термінал самообслуговування|решта в терміналі):/.test(normalize(original));
}
const payeeKey=name=>normalize(name).replace(/[^\p{L}\p{N}]+/gu,' ').trim();
function housingRules(obligations){
  const rules=new Map();
  for(const bill of obligations){
    const payee=payeeKey(bill.merchant);
    if(!payee||!['rent','utility'].includes(bill.category))continue;
    const rule=rules.get(payee)||{rents:new Set(),utility:false};
    if(bill.category==='rent'&&bill.amount>0)rule.rents.add(bill.amount);
    if(bill.category==='utility')rule.utility=true;
    rules.set(payee,rule);
  }
  return rules;
}
function updateImported(data){
  const housing=housingRules(data.obligations);
  for(const row of data.operations){
    if(!row.importKey||row.pending)continue;
    if(!row.manualType&&!row.obligation){
      if(row.type!=='expense'&&fopTransfer(row.original)){
        row.type='income';
        row.fopFunding=true;
      }else if(!row.manualCategory&&ownTransfer(row.original)){
        if(row.type!=='internal')row.bankDirection=row.type;
        row.type='internal';
      }
    }
    if(row.type!=='expense'||row.manualCategory)continue;
    if(!row.category||row.category==='unknown'||row.autoCategory===row.category){
      const category=merchantInfo(row.original,row.merchant,row.bankCategory).category;
      row.category=category!=='unknown'?category:normalize(row.original)==='на картку'?'transfers':'other';
      row.autoCategory=row.category;
    }
    applyRule(row,data.rules);
    const matched=housing.get(payeeKey(row.merchant))||housing.get(payeeKey(row.original));
    if(matched?.rents.size&&(matched.utility||matched.rents.has(row.amount))){
      row.category=matched.rents.has(row.amount)?'rent':'utility';
      row.autoCategory=row.category;
    }
    if(!data.categories[row.category]&&baseCategories[row.category])data.categories[row.category]=baseCategories[row.category];
  }
  return data;
}
function applyRule(row,rules){
  const rule=merchantRule(rules,ruleKey(row.merchant));
  if(rule&&row.type==='expense'){
    if(rule.category&&!row.manualCategory)row.category=rule.category;
    if(rule.lila!==undefined&&!row.manualLila&&!mixedMerchant(row.merchant))row.lila=rule.lila;
  }
}
function operationSheet(old=null){
  const content=$('operation-template').content.cloneNode(true);
  sheet([content]);
  const form=$('operation-form'), category=field(form,'category'), lila=field(form,'lila'), merchant=field(form,'merchant');
  const initial=old||{type:'expense',date:today(),category:'unknown',merchant:'',note:'',method:'',lila:false};
  form.querySelector('h2').textContent=old?'Операция':'Новая операция';
  categoryOptions(category);
  for(const id of ['type','date','category','merchant','note','method'])field(form,id).value=initial[id];
  field(form,'amount').value=inputMoney(initial.amount);
  field(form,'date').max=today();
  lila.checked=Boolean(initial.lila);
  $('original-description').hidden=!old?.original;
  $('original-description').textContent=old?.original?'Из выписки: '+old.original:'';
  $('delete-operation').hidden=!old;
  let categoryTouched=false,lilaTouched=false;
  category.addEventListener('change',()=>{categoryTouched=true;update();});
  lila.addEventListener('change',()=>{lilaTouched=true;update();});
  function update(){
    const expense=field(form,'type').value==='expense';
    form.querySelector('[data-lila]').hidden=!expense;
    $('rule-fields').hidden=!expense||!merchant.value.trim()||!categoryTouched&&!lilaTouched;
    field(form,'lilaRule').disabled=mixedMerchant(merchant.value);
  }
  form.addEventListener('change',update);
  merchant.addEventListener('input',()=>{
    if(!old){
      const info=merchantInfo(merchant.value,merchant.value), rule=merchantRule(state.rules,ruleKey(info.name));
      if(!categoryTouched)category.value=rule?.category||info.category;
      if(!lilaTouched)lila.checked=!mixedMerchant(info.name)&&Boolean(rule?.lila);
    }
    update();
  });
  update();
  $('delete-operation').onclick=async()=>{
    if(!confirm('Удалить эту операцию?'))return;
    if(await commit(next=>{
      next.operations=next.operations.filter(item=>item.id!==old.id);
      if(old.importKey&&!next.deleted.includes(old.importKey))next.deleted.push(old.importKey);
    }))closeSheet();
  };
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const data=formData(form), amount=financeExcel.number(data.amount);
    if(!amount||amount<0||!validDate(data.date)||data.date>today()||!methods[data.method]){
      formIssue(form,'Проверь сумму, дату и способ оплаты.');return;
    }
    const isExpense=data.type==='expense';
    const row={...old,id:old?.id||uuid(),type:data.type,amount,date:data.date,
      merchant:data.merchant.trim(),category:data.category,note:data.note.trim(),method:data.method,
      lila:isExpense&&data.lila==='on',pending:false,reason:'',
      manualType:Boolean(old?.manualType||old&&old.type!==data.type),
      manualCategory:Boolean(old?.manualCategory||categoryTouched||!old&&data.category!=='unknown'),
      manualLila:Boolean(old?.manualLila||lilaTouched)};
    if(old?.obligation&&data.type!=='expense')row.obligation=null;
    const ruleId=ruleKey(row.merchant);
    const remember=isExpense&&ruleId&&!$('rule-fields').hidden&&(data.categoryRule||data.lilaRule);
    const submitButton=form.querySelector('[type="submit"]');
    if(submitButton.disabled)return;
    submitButton.disabled=true;
    if(await commit(next=>{
      next.operations=old?next.operations.map(item=>item.id===row.id?row:item):[...next.operations,row];
      if(remember){
        const rule={...merchantRule(next.rules,ruleId)};
        if(data.categoryRule)rule.category=row.category;
        if(data.lilaRule)rule.lila=row.lila;
        Object.defineProperty(next.rules,ruleId,{value:rule,enumerable:true,writable:true,configurable:true});
        if(data.ruleScope==='past')next.operations.forEach(item=>{
          if(item.id!==row.id&&ruleKey(item.merchant)===ruleId)applyRule(item,next.rules);
        });
      }
    }))closeSheet();
    submitButton.disabled=false;
  });
}
$('manage-categories').addEventListener('click',()=>{
  const form=sheetForm('<h2>Категории</h2><label>Категория<select name="category"></select></label><label>Название<input name="name" maxlength="70" required></label><p role="status"></p><button class="lilac">Сохранить</button>');
  const select=field(form,'category'), name=field(form,'name');
  select.replaceChildren(option('','Новая категория'),...Object.entries(state.categories).map(([id,label])=>option(id,label)));
  select.addEventListener('change',()=>{name.value=state.categories[select.value]||'';});
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const value=name.value.trim(), id=select.value||uuid();
    if(!value)return;
    if(Object.entries(state.categories).some(([other,label])=>other!==id&&normalize(label)===normalize(value))){
      formIssue(form,'Категория с таким названием уже есть.');return;
    }
    if(await commit(next=>{next.categories[id]=value;}))closeSheet();
  });
});

function importSheet(){
  const title=n('h2','Импорт выписки');
  const hint=empty('Выбери выписку .xlsx из Приват24. В одном файле могут быть операции по нескольким гривневым картам.');
  const file=n('input');file.type='file';file.accept='.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  file.setAttribute('aria-label','Выписка Excel');
  const status=n('p');status.setAttribute('role','status');
  const secret=key;
  file.addEventListener('change',async()=>{
    if(!file.files.length)return;
    file.disabled=true;status.textContent='Читаю выписку…';
    try{
      const result=await financeExcel.read(file.files[0]);
      if(key!==secret)return;
      if(await importRows(result)){
        closeSheet();openView('review');
      }else status.textContent='Импорт не сохранён. Проверь сообщение на странице.';
    }catch(error){status.textContent=error?.message||'Не удалось открыть выписку.';}
    finally{file.disabled=false;file.value='';}
  });
  sheet([title,hint,file,status]);
}
function classifyBank(row){
  const text=normalize(row.original);
  if(row.amount<0&&/^(?:комісія|комиссия|bank fee)(?:\s|$)/.test(text))return {type:'expense',category:'bank'};
  if(row.amount>0&&fopTransfer(row.original))return {type:'income',fopFunding:true};
  if(ownTransfer(row.original))return {type:'internal',bankDirection:row.amount<0?'expense':'income'};
  const type=row.amount<0?'expense':'income';
  if(/крипт|crypto|зняття готівки|снятие налич|поповнення готівкою|внесення готівки|пополнение налич|переказ|перевод/.test(text)){
    return {type,pending:true,reason:'Уточни, это доход, расход или перемещение своих денег.'};
  }
  return {type};
}
async function importRows({rows,skipped}){
  const batchId=uuid(), occurrence=new Map(), cards=new Map(), incoming=[];
  for(const row of rows){
    if(row.date>today()){skipped++;continue;}
    if(row.card&&!cards.has(row.card))cards.set(row.card,await digest('card:'+row.card));
    const cardId=cards.get(row.card)||'';
    const cardTail=row.card?.match(/\d{4}$/)?.[0]||'';
    const signature=JSON.stringify([row.date,row.time,row.amount,normalize(row.original)]);
    const scope=cardId?cardId+':':'';
    const occurrenceKey=scope+signature;
    const count=(occurrence.get(occurrenceKey)||0)+1;
    occurrence.set(occurrenceKey,count);
    const identity=row.bankId?'bank:'+row.bankId:'row:'+signature+':'+count;
    const legacyKey=await digest(identity);
    const importKey=scope?await digest(scope+identity):legacyKey;
    incoming.push({row,importKey,legacyKey,cardId,cardTail});
  }
  return commit(next=>{
    let added=0,pending=0;
    const seen=new Set([...next.deleted,...next.operations.map(row=>row.importKey).filter(Boolean)]);
    const byImportKey=new Map(next.operations.filter(row=>row.importKey).map(row=>[row.importKey,row]));
    const legacy=new Map(next.operations.filter(row=>row.importKey&&!row.cardId).map(row=>[row.importKey,row]));
    const addBankFields=(saved,row)=>{
      if(saved){
        if(row.bankCategory)saved.bankCategory=row.bankCategory;
        if(row.transactionAmount!=null)saved.transactionAmount=row.transactionAmount;
      }
    };
    const aliases=new Set(next.operations.map(row=>row.legacyImportKey).filter(Boolean));
    const deleted=new Set(next.deleted);
    const byAmount=new Map();
    const matchKey=row=>row.date+':'+Math.abs(row.amount);
    for(const item of next.operations){
      const k=matchKey(item), list=byAmount.get(k)||[];
      list.push(item);byAmount.set(k,list);
    }
    for(const {row,importKey,legacyKey,cardId,cardTail} of incoming){
      if(seen.has(importKey)||!cardId&&aliases.has(legacyKey)){
        addBankFields(byImportKey.get(importKey),row);
        skipped++;
        continue;
      }
      // Keep previously edited operations and exclusions when a later export supplies the card.
      const old=cardId&&legacy.get(legacyKey);
      if(cardId&&(deleted.has(legacyKey)||old&&normalize(old.original)===normalize(row.original))){
        if(deleted.delete(legacyKey))deleted.add(importKey);
        if(old){
          Object.assign(old,{importKey,legacyImportKey:legacyKey,cardId,cardTail});
          addBankFields(old,row);
          legacy.delete(legacyKey);
          aliases.add(legacyKey);
        }
        seen.delete(legacyKey);
        seen.add(importKey);
        skipped++;
        continue;
      }
      const previous=byAmount.get(matchKey(row))||[];
      const classification=classifyBank(row);
      const possible=previous.some(item=>!(cardId&&item.cardId&&cardId!==item.cardId)&&
        !(row.bankId&&item.bankId&&row.bankId!==item.bankId)&&normalize(item.original||item.merchant)!==normalize(row.original)&&
        item.type===classification.type);
      const info=merchantInfo(row.original,row.merchant,row.bankCategory);
      const item={id:uuid(),batchId,importKey,date:row.date,time:row.time,amount:Math.abs(row.amount),original:row.original,
        bankId:row.bankId,cardId,cardTail,legacyImportKey:cardId?legacyKey:'',bankCategory:row.bankCategory,transactionAmount:row.transactionAmount,autoCategory:classification.category||info.category,
        merchant:info.name,category:info.category,method:'card',note:'',lila:false,...classification};
      if(possible){item.pending=true;item.reason='Возможный дубликат: совпадают дата и сумма.';item.duplicate=true;}
      applyRule(item,next.rules);
      next.operations.push(item);
      seen.add(importKey);
      if(cardId)aliases.add(legacyKey);
      const k=matchKey(item), list=byAmount.get(k)||[];
      list.push(item);byAmount.set(k,list);
      if(item.pending)pending++;
      else added++;
    }
    next.deleted=[...deleted];
    if(added+pending)next.lastImport={id:batchId,added,pending,skipped};
    else if(next.lastImport)next.lastImport.latestSkipped=skipped;
    else next.lastImport={id:null,added,pending,skipped};
  });
}
function renderReview(){
  const last=state.lastImport;
  const pending=state.operations.filter(row=>row.pending);
  const unknown=state.operations.filter(row=>!row.pending&&row.batchId===last?.id&&['unknown','other','transfers'].includes(row.category)&&row.type==='expense');
  $('import-summary').textContent=last?(last.latestSkipped!=null?'При повторной загрузке пропущено: '+last.latestSkipped+'. ':
    'Добавлено сразу: '+last.added+' · отправлено на проверку: '+last.pending+' · пропущено: '+last.skipped+'.'):'Выписки ещё не загружались.';
  $('undo-import').disabled=!last?.id;
  const display=[];
  if(pending.length)display.push(n('h2','Нужно проверить'));
  for(const row of pending){
    const card=n('article','','card');
    card.append(n('strong',row.merchant+' · '+money(row.amount)),empty(shortDate(row.date)+' · '+row.reason),empty(row.original));
    const actions=n('div','','actions');
    actions.append(button(row.duplicate?'Это новая операция':'Уточнить тип',()=>operationSheet(row),'lilac'),
      button(row.duplicate?'Уже существует':'Исключить',()=>commit(next=>{
        next.operations=next.operations.filter(item=>item.id!==row.id);
        if(!next.deleted.includes(row.importKey))next.deleted.push(row.importKey);
      })));
    card.append(actions);display.push(card);
  }
  if(unknown.length)display.push(n('h2','Уточнить назначение'),...unknown.map(operationRow));
  const latest=state.operations.filter(row=>!row.pending&&row.batchId===last?.id&&!unknown.includes(row));
  if(latest.length){
    const imported=n('details','','card');imported.append(n('summary','Операции последнего импорта'),...latest.map(operationRow));
    display.push(imported);
  }
  $('review-list').replaceChildren(...(display.length?display:[empty('Нет операций, которые нужно проверить.')]));
}
$('undo-import').addEventListener('click',async()=>{
  if(!state.lastImport?.id||!confirm('Удалить операции, добавленные последним импортом?'))return;
  await commit(next=>{
    const rows=next.operations.filter(row=>row.batchId===next.lastImport.id);
    const keys=new Set(rows.map(row=>row.importKey));
    next.operations=next.operations.filter(row=>row.batchId!==next.lastImport.id);
    next.deleted=next.deleted.filter(importKey=>!keys.has(importKey));
    next.lastImport=null;
  });
});
function monthAt(month,offset){
  const date=new Date(month+'-01');
  date.setUTCMonth(date.getUTCMonth()+offset);
  return isoMonth(date.toISOString());
}
function obligationMonth(){return isoMonth(range.end);}
function chargesInMonth(bill,month){
  if(!bill.intervalDays)return 1;
  const anchor=Date.parse(bill.chargeStart), interval=bill.intervalDays*86400000;
  const first=Math.max(0,Math.ceil((Date.parse(month+'-01')-anchor)/interval));
  const last=Math.floor((Date.parse(monthEnd(month))-anchor)/interval);
  return Math.max(0,last-first+1);
}
function obligationPeriods(bill,target){
  const interval=bill.intervalDays?1:bill.interval||1, result=[];
  for(let month=bill.start,i=0;month<=target&&i<2400;i++,month=monthAt(month,interval)){
    if(chargesInMonth(bill,month))result.push(month);
  }
  return result;
}
function billPayments(id,period){
  return state.operations.filter(row=>!row.pending&&row.type==='expense'&&row.obligation?.id===id&&row.obligation.period===period);
}
function billStatus(bill,period,through){
  const base=bill.amountFrom&&period<bill.amountFrom?null:bill.amount;
  const expected=bill.expected?.[period]??(base==null?null:base*chargesInMonth(bill,period));
  const payments=billPayments(bill.id,period).filter(row=>row.date<=through);
  const paid=payments.reduce((sum,row)=>sum+row.amount,0);
  const historical=bill.covered&&period<=bill.covered;
  return {expected,paid,payments,left:historical?0:expected==null?null:Math.max(0,expected-paid),historical};
}
function renderObligations(){
  const month=obligationMonth(), through=range.end;
  let paid=0,left=0,unknown=0;
  const rows=[];
  for(const bill of state.obligations){
    for(const period of obligationPeriods(bill,month)){
      const status=billStatus(bill,period,through);
      if(period!==month&&(status.left===0||(bill.ended&&period>bill.ended)))continue;
      if(bill.ended&&period>bill.ended)continue;
      paid+=status.paid;
      left+=status.left||0;
      unknown+=status.left===null?1:0;
      const label=status.historical?'Оплачено ранее':status.left===0?'Оплачено':status.paid?'Частично оплачено':'Не оплачено';
      rows.push(rowButton(bill.name,monthName(period)+' · '+label+(period!==month?' · перенесено':''),
        status.historical?'✓':status.left===null?'Уточнить сумму':status.left===0?'✓':money(status.left),()=>billSheet(bill,period)));
    }
  }
  $('obligation-summary').textContent=rows.length?'Оплачено '+money(paid)+' · осталось '+money(left)+(unknown?' · есть суммы к уточнению':''):'Нет обязательств';
  $('obligation-list').replaceChildren(...(rows.length?rows:[empty('На '+monthName(month)+' обязательств нет.')]));
}
function obligationForm(old=null){
  const form=sheetForm('<h2>Обязательство</h2><label>Название<input name="name" maxlength="90" required></label><label>Получатель<input name="merchant" maxlength="160"></label><div class="grid"><label>Первый месяц<input name="start" type="month" required></label><label>Сумма, грн<input name="amount" inputmode="decimal" placeholder="Если фиксированная"></label></div><label>Категория<select name="category"></select></label><label>Способ оплаты<select name="method"><option value="card">Карта</option><option value="cash">Наличные</option></select></label><div class="grid"><label>Ранее оплачено по<input name="covered" type="month"></label><label>Последний месяц, если завершено<input name="ended" type="month"></label></div><p class="muted">Период «Ранее оплачено по» отмечает старые обязательства без создания расходов.</p><p role="status"></p><button class="lilac">Сохранить</button>');
  categoryOptions(field(form,'category'));
  field(form,'start').value=old?.start||obligationMonth();
  if(old){
    for(const id of ['name','merchant','category','method','covered','ended'])field(form,id).value=old[id]||'';
    field(form,'amount').value=inputMoney(old.amount);
    field(form,'start').disabled=true;
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const data=formData(form), start=old?.start||data.start;
    const amount=data.amount.trim()?financeExcel.number(data.amount):null;
    if(!data.name.trim()||!validDate(start+'-01')||(data.amount.trim()&&!(amount>0))||
      [data.covered,data.ended].some(month=>month&&(!validDate(month+'-01')||month<start))){
      formIssue(form,'Проверь название, периоды и сумму.');return;
    }
    const bill={...old,id:old?.id||uuid(),name:data.name.trim(),merchant:data.merchant.trim(),
      start,amount,category:data.category,method:data.method,covered:data.covered,ended:data.ended};
    if(await commit(next=>{
      next.obligations=old?next.obligations.map(item=>item.id===old.id?bill:item):[...next.obligations,bill];
    }))closeSheet();
  });
}
$('add-obligation').addEventListener('click',()=>obligationForm());
$('bill-presets').addEventListener('change',async event=>{
  const file=event.target.files[0];
  event.target.value='';
  if(!file)return;
  try{
    if(file.size>50000)throw new Error();
    const presets=JSON.parse(await file.text());
    if(presets.version!==1||!Array.isArray(presets.bills)||presets.bills.length>30)throw new Error();
    const month=value=>typeof value==='string'&&validDate(value+'-01');
    const rows=presets.bills.map(bill=>{
      const string=(value,max)=>typeof value==='string'&&value.length<=max;
      if(!bill||!string(bill.id,80)||!string(bill.name,90)||!bill.name.trim()||!string(bill.merchant,160)||
        !month(bill.start)||!Object.hasOwn(baseCategories,bill.category)||!Object.hasOwn(methods,bill.method)||
        bill.amount!==null&&(!Number.isSafeInteger(bill.amount)||bill.amount<=0||bill.amount>1e12)||
        bill.covered&&!month(bill.covered)||bill.amountFrom&&!month(bill.amountFrom))throw new Error();
      return {id:'preset-'+bill.id,name:bill.name.trim(),merchant:bill.merchant.trim(),category:bill.category,
        start:bill.start,amount:bill.amount,amountFrom:bill.amountFrom||'',covered:bill.covered||'',method:bill.method,lila:bill.lila===true};
    });
    let count=0;
    if(await commit(next=>{
      for(const bill of rows){
        if(!next.obligations.some(row=>row.id===bill.id||normalize(row.name)===normalize(bill.name))){
          next.obligations.push(bill);count++;
        }
      }
    }))issue(count?'Добавлено шаблонов: '+count+'. Расходы не созданы.':'Эти обязательства уже есть.');
  }catch{issue('Не удалось прочитать шаблоны обязательств.');}
});

function billSheet(bill,period){
  const status=billStatus(bill,period,today());
  const form=n('form');
  form.innerHTML='<label>Ожидаемая сумма за этот месяц, грн<input name="expected" inputmode="decimal"></label><p role="status"></p><button>Обновить сумму</button>';
  field(form,'expected').value=inputMoney(status.expected);
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const value=financeExcel.number(field(form,'expected').value);
    if(!(value>0)){formIssue(form,'Укажи сумму больше нуля.');return;}
    if(await commit(next=>{
      const row=next.obligations.find(item=>item.id===bill.id);
      row.expected={...row.expected,[period]:value};
    }))closeSheet();
  });
  const actions=n('div','','actions');
  actions.append(button('Связать с операцией',()=>linkBill(bill,period),'lilac'),button('Записать оплату',()=>billPaymentForm(bill,period)),
    button('Настройки',()=>obligationForm(bill)));
  const paid=status.payments.map(row=>{
    const item=n('div','','actions');
    item.append(n('span',shortDate(row.date)+' · '+money(row.amount)+' · '+methods[row.method]),
      button('Отвязать',async()=>{
        if(await commit(next=>{next.operations.find(item=>item.id===row.id).obligation=null;}))closeSheet();
      }));
    return item;
  });
  sheet([n('h2',bill.name),empty(monthName(period)),n('p',status.historical?'Период отмечен как оплаченный ранее.':'Учтено фактических оплат: '+money(status.paid)),...paid,form,actions]);
}
function linkBill(bill,period){
  const rows=state.operations.filter(row=>!row.pending&&row.type==='expense'&&!row.obligation);
  const preferred=row=>Number(normalize(row.merchant)===normalize(bill.merchant)&&Boolean(bill.merchant))*2+Number(row.category===bill.category);
  rows.sort((a,b)=>preferred(b)-preferred(a)||b.date.localeCompare(a.date));
  const form=sheetForm('<h2>Связать оплату</h2><p class="muted">Выбери уже записанный расход. Вторая операция не создаётся.</p><label>Операция<select name="operation" required></select></label><p role="status"></p><button class="lilac">Связать</button>');
  const select=field(form,'operation');
  select.replaceChildren(option('','Выбрать'),...rows.map(row=>option(row.id,shortDate(row.date)+' · '+(row.merchant||categoryName(row.category))+' · '+money(row.amount))));
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const id=select.value;
    if(await commit(next=>{
      const row=next.operations.find(item=>item.id===id);
      if(!row||row.obligation)throw new Error('Операция уже связана или удалена.');
      row.obligation={id:bill.id,period};
    }))closeSheet();
  });
}
function billPaymentForm(bill,period){
  const form=sheetForm('<h2>Записать фактическую оплату</h2><p class="muted">Если оплата уже есть в истории, свяжи её с обязательством.</p><div class="grid"><label>Сумма, грн<input name="amount" inputmode="decimal" required></label><label>Дата<input name="date" type="date" required></label></div><label>Способ оплаты<select name="method"><option value="card">Карта</option><option value="cash">Наличные</option></select></label><label class="check"><input type="checkbox" name="lila">Лила</label><p role="status"></p><button class="lilac">Записать</button>');
  field(form,'date').value=today();field(form,'date').max=today();
  field(form,'method').value=bill.method;
  field(form,'lila').checked=Boolean(bill.lila);
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const data=formData(form), amount=financeExcel.number(data.amount);
    if(!(amount>0)||!validDate(data.date)||data.date>today()){formIssue(form,'Проверь сумму и дату.');return;}
    const duplicate=state.operations.some(row=>row.type==='expense'&&row.amount===amount&&row.date===data.date&&row.method===data.method);
    if(duplicate&&!confirm('Есть расход на ту же дату и сумму. Записать отдельную оплату?'))return;
    if(await commit(next=>{next.operations.push({id:uuid(),date:data.date,amount,type:'expense',method:data.method,
      category:bill.category,merchant:bill.merchant||bill.name,note:bill.name,lila:data.lila==='on',
      manualCategory:true,manualLila:true,obligation:{id:bill.id,period}});}))closeSheet();
  });
}

function renderAnalytics(){
  $('analytics-period').textContent=range.label+' ⌄';
  $('analytics-lila').setAttribute('aria-pressed',String(analyticsLila));
  $('analytics-lila').classList.toggle('lilac',analyticsLila);
  const rows=operations(range,analyticsLila), summary=totals(rows,range);
  const parts=[n('div','','card sage')];
  parts[0].append(...stats(summary));
  const categories=n('section','','card');categories.append(n('h2','Категории'));
  for(const [id,value] of group(rows,row=>row.category)){
    categories.append(rowButton(categoryName(id),'',money(value.amount),()=>drill(id,'',analyticsLila)));
  }
  const merchants=n('section','','card');merchants.append(n('h2','Магазины и получатели'));
  for(const [merchant,value] of group(rows,row=>normalize(row.merchant))){
    const name=rows.find(row=>normalize(row.merchant)===merchant)?.merchant||'Без получателя';
    merchants.append(rowButton(name,/uklon|уклон/.test(merchant)?value.count+' списаний':'',money(value.amount),()=>drill('',merchant||':empty:',analyticsLila)));
  }
  const top=n('section','','card');top.append(n('h2','10 крупнейших расходов'));
  top.append(...rows.filter(row=>row.type==='expense').sort((a,b)=>b.amount-a.amount).slice(0,10).map(operationRow));
  if(summary.expense)parts.push(categories,merchants,top);
  else parts.push(empty('За этот период расходов нет.'));
  $('analytics-content').replaceChildren(...parts);
  const output=$('comparison');output.replaceChildren();
  if(compare){
    const prior=totals(operations(compare,analyticsLila),compare), card=n('section','','card');
    const percent=(value,base)=>base?' · '+new Intl.NumberFormat('ru-RU',{signDisplay:'exceptZero',maximumFractionDigits:1}).format((value-base)/Math.abs(base)*100)+'%':'';
    card.append(n('h2','Сравнение'),empty(shortDate(compare.start)+' — '+shortDate(compare.end)+' / '+shortDate(range.start)+' — '+shortDate(range.end)),
      metric('Поступления',signed(summary.income-prior.income)+percent(summary.income,prior.income)),
      metric('Расходы',signed(summary.expense-prior.expense)+percent(summary.expense,prior.expense)),
      metric('Разница',signed(summary.difference-prior.difference)+percent(summary.difference,prior.difference)),
      metric('Расход в день',signed(summary.average-prior.average)+percent(summary.average,prior.average)));
    if(compare.end===today()||range.end===today())card.append(empty('Один из периодов показан по сегодняшний день.'));
    card.append(button('Убрать сравнение',()=>{compare=null;renderAnalytics();}));
    output.append(card);
  }
}
$('analytics-lila').addEventListener('click',()=>{analyticsLila=!analyticsLila;renderAnalytics();});

function subscriptionRows(name){
  const merchant=normalize(name);
  return state.operations.filter(row=>!row.pending&&row.type==='expense'&&normalize(row.merchant)===merchant)
    .sort((a,b)=>b.date.localeCompare(a.date));
}
const dayGap=(a,b)=>Math.round((Date.parse(a)-Date.parse(b))/86400000);
function subscriptionCandidates(){
  const groups=group(state.operations.filter(row=>!row.pending&&row.method==='card'&&row.merchant),row=>normalize(row.merchant));
  const result=[];
  for(const [merchant,{count}] of groups){
    if(count<2||state.dismissed.includes(merchant)||state.subscriptions.some(row=>normalize(row.name)===merchant))continue;
    const rows=subscriptionRows(merchant);
    const [latest,previous,third]=rows;
    const gap=dayGap(latest.date,previous.date);
    const nearYear=gap>=355&&gap<=375, nearMonth=gap>=26&&gap<=34;
    const repeated=third&&Math.abs(dayGap(previous.date,third.date)-gap)<=3&&gap>=7;
    if((nearYear||nearMonth||repeated)&&latest.amount===previous.amount&&(!/apple|itunes/.test(merchant)||third&&repeated)){
      result.push({name:latest.merchant,amount:latest.amount,unit:nearYear||nearMonth?'months':'days',
        interval:nearYear?12:nearMonth?1:gap,last:latest.date});
    }
  }
  return result;
}
function nextCharge(last,unit,interval){
  if(!last)return '';
  if(unit==='months'){
    const month=monthAt(isoMonth(last),interval);
    return month+'-'+String(Math.min(Number(last.slice(8)),Number(monthEnd(month).slice(8)))).padStart(2,'0');
  }
  return new Date(Date.parse(last)+interval*86400000).toISOString().slice(0,10);
}
function renderSubscriptions(){
  const content=[];
  for(const sub of state.subscriptions){
    const rows=subscriptionRows(sub.name), latest=rows[0];
    const date=nextCharge(latest?.date||sub.last,sub.unit,sub.interval);
    const shownCost=latest&&(!sub.last||latest.date>sub.last)?latest.amount:sub.amount;
    const card=n('article','','card');
    card.append(n('h2',sub.name),n('p',money(shownCost)+' · интервал '+sub.interval+(sub.unit==='months'?' мес.':' дн.')),
      empty((date?'Следующее списание ориентировочно '+shortDate(date)+'. ':'')+(sub.required?'В обязательных платежах.':'')));
    if(rows.length){
      const details=n('details');details.append(n('summary','История оплат'),...rows.map(operationRow));card.append(details);
    }
    card.append(button('Изменить',()=>subscriptionForm(sub)));
    content.push(card);
  }
  const candidates=subscriptionCandidates();
  if(candidates.length)content.push(n('h2','Похожие на подписки'));
  for(const sub of candidates){
    const card=n('article','','card'), actions=n('div','','actions');
    card.append(n('strong',sub.name),empty(money(sub.amount)+' · регулярные списания'));
    actions.append(button('Подтвердить',()=>subscriptionForm(sub),'lilac'),button('Пропустить',()=>commit(next=>{next.dismissed.push(normalize(sub.name));})));
    card.append(actions);content.push(card);
  }
  $('subscription-list').replaceChildren(...(content.length?content:[empty('Пока нет подписок и подходящих списаний.')]));
}
function subscriptionForm(old={}){
  const form=sheetForm('<h2>Подписка</h2><label>Сервис<input name="name" maxlength="160" required></label><div class="grid"><label>Стоимость, грн<input name="amount" inputmode="decimal" required></label><label>Последнее списание<input name="last" type="date"></label><label>Интервал<input name="interval" type="number" min="1" max="365" value="1" required></label><label>Единица<select name="unit"><option value="months">Месяцы</option><option value="days">Дни</option></select></label></div><label class="check"><input type="checkbox" name="required">Включить в обязательные платежи</label><p role="status"></p><button class="lilac">Сохранить</button>');
  for(const id of ['name','last','interval','unit'])if(old[id]!=null)field(form,id).value=old[id];
  field(form,'amount').value=inputMoney(old.amount);
  field(form,'required').checked=Boolean(old.required);
  field(form,'last').max=today();
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const data=formData(form),amount=financeExcel.number(data.amount);
    const interval=Number(data.interval);
    if(!data.name.trim()||!(amount>0)||!Number.isInteger(interval)||interval<1||interval>365||
      (data.last&&(!validDate(data.last)||data.last>today()))){
      formIssue(form,'Проверь название, сумму, дату и интервал.');return;
    }
    const sub={...old,id:old.id||uuid(),name:data.name.trim(),amount,interval,unit:data.unit,last:data.last,required:data.required==='on'};
    if(await commit(next=>{
      next.subscriptions=old.id?next.subscriptions.map(item=>item.id===sub.id?sub:item):[...next.subscriptions,sub];
      const existing=next.obligations.find(row=>row.subscription===sub.id);
      if(!sub.required){
        if(existing)existing.ended=monthAt(isoMonth(today()),-1);
        return;
      }
      const chargeStart=existing?.chargeStart||nextCharge(sub.last,sub.unit,sub.interval)||today();
      const bill={...existing,id:existing?.id||uuid(),subscription:sub.id,name:sub.name,merchant:sub.name,
        category:'digital',method:'card',amount:sub.amount,interval:sub.unit==='months'?sub.interval:1,
        intervalDays:sub.unit==='days'?sub.interval:0,chargeStart,
        start:existing?.start||isoMonth(chargeStart),ended:''};
      next.obligations=existing?next.obligations.map(row=>row.id===existing.id?bill:row):[...next.obligations,bill];
    }))closeSheet();
  });
}
$('add-subscription').addEventListener('click',()=>subscriptionForm());
function exportRows(){
  return operations().filter(matchesHistory).sort((a,b)=>a.date.localeCompare(b.date));
}
function download(blob,name){
  const url=URL.createObjectURL(blob), link=n('a');
  link.href=url;link.download=name;
  document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),60000);
}
const exportHeaders=['Дата','Тип','Сумма, грн','Категория','Магазин или получатель','Способ оплаты','Комментарий','Лила','Описание из банка'];
function exportValues(row){
  return [row.date,operationTypeLabel(row),row.amount/100,categoryName(row.category),row.merchant,methods[row.method],row.note,row.lila?'Да':'',row.original];
}
function reportTitle(){return 'Личный бюджет · '+range.start+' — '+range.end;}
async function exportExcel(){
  const rows=exportRows(), result=totals(rows,range);
  try{
    const file=await financeExcel.write([
      {name:'Операции',rows:[exportHeaders,...rows.map(exportValues)]},
      {name:'Сводка',rows:[[reportTitle()],['Поступило в бюджет, грн',result.income/100],['В том числе с ФОП, грн',result.fop/100],['Потрачено, грн',result.expense/100],
        ['Разница, грн',result.difference/100],['Средний расход, грн',result.average/100],
        [],['Категория','Расход, грн'],...group(rows,row=>row.category).map(([id,value])=>[categoryName(id),value.amount/100])]}
    ]);
    if(key)download(file,'life-budget-'+range.start+'.xlsx');
  }catch{issue('Не удалось подготовить Excel.');}
}
function printBudget(){
  const rows=exportRows(), report=n('article','','print-report');
  report.append(n('h1',reportTitle()),...stats(totals(rows,range)));
  report.append(n('h2','Категории'),...group(rows,row=>row.category).map(([id,value])=>metric(categoryName(id),money(value.amount))));
  report.append(n('h2','Крупнейшие расходы'));
  for(const row of rows.filter(item=>item.type==='expense').sort((a,b)=>b.amount-a.amount).slice(0,10)){
    report.append(metric(row.merchant||categoryName(row.category),money(row.amount)));
  }
  const table=n('table'), header=n('thead'), body=n('tbody');
  const addRow=(parent,tag,values)=>{
    const line=n('tr');
    line.append(...values.map(value=>n(tag,String(value??''))));parent.append(line);
  };
  addRow(header,'th',['Дата','Тип','Сумма','Получатель и детали']);
  for(const row of rows)addRow(body,'td',[row.date,operationTypeLabel(row),money(row.amount),
    [row.merchant,categoryName(row.category),methods[row.method],row.lila?'Лила':'',row.note,row.original].filter(Boolean).join(' · ')]);
  table.append(header,body);
  report.append(n('h2','Операции'),table);
  document.querySelector('.print-report')?.remove();
  document.body.append(report);
  closeSheet();
  window.print();
  report.remove();
}
function downloadBackup(){
  download(new Blob([JSON.stringify(record)],{type:'application/json'}),'life-budget-backup-'+today()+'.json');
}
$('export-menu').addEventListener('click',()=>{
  const actions=n('div','','sheet-menu');
  actions.append(button('Скачать Excel',exportExcel),button('Сохранить PDF через печать',printBudget),
    button('Скачать зашифрованную копию',downloadBackup));
  const picker=n('input');
  picker.type='file';picker.accept='.json,application/json';picker.setAttribute('aria-label','Выбрать копию бюджета');
  picker.addEventListener('change',()=>{if(picker.files[0])restoreSheet(picker.files[0]);});
  sheet([n('h2','Экспорт и копии'),empty('Excel и PDF учитывают период и фильтры истории. Копия сохраняет весь личный бюджет. Для восстановления понадобится PIN этой копии.'),actions,picker]);
});
$('locked-backup').addEventListener('change',event=>{
  const file=event.target.files[0];event.target.value='';
  if(file)restoreSheet(file);
});
function restoreSheet(file){
  const form=sheetForm('<h2>Восстановить бюджет</h2><p class="muted">Введи PIN, с которым была создана копия.</p><label>PIN копии<input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6,12}" required></label><p role="status"></p><button class="lilac">Проверить и восстановить</button>');
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    if(busy)return;
    busy=true;
    const submit=form.querySelector('button');submit.disabled=true;
    try{
      await saveQueue;
      if(file.size>50000000)throw new Error('Копия слишком большая.');
      const backup=JSON.parse(await file.text());
      if(backup.version!==1||typeof backup.data!=='string'||decode64(backup.salt).length!==16||decode64(backup.iv).length!==12){
        throw new Error('Это не резервная копия личного бюджета.');
      }
      const secret=await derive(field(form,'pin').value,decode64(backup.salt));
      const loaded=await decrypt(backup,secret);
      if(record&&!confirm('Восстановление заменит текущий личный бюджет. Продолжить?'))return;
      const restored=await encrypt(loaded,secret,decode64(backup.salt));
      await writeVault(restored,record?.revision||null);
      record=restored;
      issue('Бюджет восстановлен. Войди с PIN этой копии.');
      showGate();
    }catch(error){
      formIssue(form,error.name==='OperationError'?'PIN копии не подошёл или файл повреждён.':error.message||'Не удалось восстановить бюджет.');
    }finally{busy=false;submit.disabled=false;}
  });
}

(async()=>{
  try{
    if(!crypto.subtle)throw new Error('Открой «Финансы» по HTTPS или через локальный предпросмотр.');
    db=await openDatabase();
    record=await readLocalVault();
    if(showRecoveryCallback())return;
    const owner=financeCloud.session()?.user?.id;
    if(owner){
      try{if(await selectCloud(owner,{automatic:true}))return;}
      catch(error){
        if(knownCloud(owner)){
          cloudOwner=owner;record=null;showGate();
          issue(error.message||'Общие записи недоступны. Проверь соединение.');
          return;
        }
      }
    }
    showGate();
  }catch(error){
    issue(error.message||'Не удалось открыть хранилище браузера.');
  }
})();