'use strict';

const financeExcel = (() => {
  const localName = (node, name) => [...node.getElementsByTagNameNS('*',name)];
  const parse = text => {
    const doc = new DOMParser().parseFromString(text,'application/xml');
    if (doc.querySelector('parsererror')) throw new Error('Не удалось прочитать структуру Excel.');
    return doc;
  };
  const words = value => String(value ?? '').normalize('NFKC').toLowerCase().replace(/[’']/g,'').replace(/\s+/g,' ').trim();
  function number(value) {
    const normalized = String(value ?? '').replace(/(?:uah|грн|₴)\s*$/i,'').replace(/[\s\u00a0\u202f]/g,'').replace(/[−–]/g,'-').replace(/,/g,'.');
    if(!/^[+-]?\d+(?:\.\d{1,2})?$/.test(normalized))return null;
    const cents = Math.round(Number(normalized)*100);
    return Number.isSafeInteger(cents) && Math.abs(cents)<=1e12 ? cents : null;
  }
  function excelDate(value, epoch) {
    let date, time='';
    const raw = String(value ?? '').trim();
    if (/^\d{4,6}(?:\.\d+)?$/.test(raw)) {
      const serial = Number(raw), day=Math.floor(serial);
      if(day>100000)return null;
      date = new Date(epoch+day*86400000).toISOString().slice(0,10);
      time = new Date(Math.floor((serial-day)*86400+.00001)*1000).toISOString().slice(11,19);
    } else {
      const local = raw.match(/^(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})(?:\s+(\d{1,2}:\d{2}(?::\d{2})?))?$/);
      const iso = raw.match(/^(\d{4}-\d{2}-\d{2})(?:[T ](\d{1,2}:\d{2}(?::\d{2})?))?$/);
      if(local) {
        date = [local[3],local[2].padStart(2,'0'),local[1].padStart(2,'0')].join('-');
        time = local[4] || '';
      } else if (iso) {
        [,date,time=''] = iso;
      }
      if (time) {
        const [h,m,s='00']=time.split(':');
        time=h.padStart(2,'0')+':'+m+':'+s;
      }
    }
    return date && Number.isFinite(Date.parse(date)) && new Date(date).toISOString().slice(0,10)===date
      ? {date,time} : null;
  }
  function cells(row, shared) {
    const values=[];
    for (const cell of localName(row,'c')) {
      const ref=cell.getAttribute('r')?.match(/^[A-Z]+/)?.[0];
      const i=ref?[...ref].reduce((col,ch)=>col*26+ch.charCodeAt(0)-64,0)-1:values.length;
      const type=cell.getAttribute('t'), value=localName(cell,'v')[0]?.textContent ?? '';
      values[i] = type==='s' ? shared[Number(value)] ?? '' : type==='inlineStr' ? localName(cell,'t').map(t=>t.textContent).join('') : value;
    }
    return values;
  }
  function columns(values) {
    const find = re => values.findIndex(value=>re.test(words(value)));
    const date=find(/(?:дата|date)(?:[\s,/(]|$)/);
    const time=find(/^(?:час|время|time)$/);
    const description=find(/опис|описание|призначення|назначение|деталі|description|merchant|контрагент/);
    const amount=find(/(?:сума|сумма|amount).*(?:рахунк|счет|счёт|карт|account|грн|uah)/);
    const generic=find(/^(?:сума|сумма|amount)(?:$|\s)/);
    const debit=find(/^дебет|^debit|^витрати|^списання/);
    const credit=find(/^кредит|^credit|^надходження|^зарахування/);
    const currency=find(/^(?:валют.*(?:рахунк|карт|счет|счёт)|account currency)/);
    const anyCurrency=find(/^(?:валюта|currency)$/);
    const bankId=find(/(?:^id$|rrn|reference|ідентифікатор|идентификатор|номер операції|номер операции|^референс)/);
    const card=find(/^(?:картка|карта|номер картки|номер карты|card number|рахунок|iban)$/);
    const direction=find(/^(?:тип|вид|напрямок|направление|direction|type)(?:\s+операц.*)?$/);
    const merchant=find(/(?:магазин|отримувач|получатель|merchant|контрагент)/);
    return date>=0&&description>=0&&(amount>=0||generic>=0||(debit>=0&&credit>=0))
      ? {date,time,description,amount:amount>=0?amount:generic,debit,credit,currency:currency>=0?currency:amount<0?anyCurrency:-1,bankId,card,direction,merchant}:null;
  }
  async function read(file) {
    if(file.size>15000000)throw new Error('Файл больше 15 МБ. Раздели выписку на несколько периодов.');
    const zip=await JSZip.loadAsync(await file.arrayBuffer());
    const readXml=async name=>{
      const item=zip.file(name);
      if(!item)return null;
      const data=await item.async('string');
      if(data.length>35000000)throw new Error('Таблица слишком большая. Раздели выписку по периодам.');
      return parse(data);
    };
    const book=await readXml('xl/workbook.xml');
    const rels=await readXml('xl/_rels/workbook.xml.rels');
    if(!book||!rels)throw new Error('Выбери банковскую выписку в формате .xlsx.');
    const sharedDoc=await readXml('xl/sharedStrings.xml');
    const shared=sharedDoc?localName(sharedDoc,'si').map(row=>localName(row,'t').map(t=>t.textContent).join('')):[];
    const epoch=Date.UTC(1899,11,30)+(['1','true'].includes(localName(book,'workbookPr')[0]?.getAttribute('date1904'))?1462*86400000:0);
    const paths=new Map(localName(rels,'Relationship').map(item=>[item.getAttribute('Id'),item.getAttribute('Target')]));
    const parsed=[];
    let skipped=0, recognized=false;
    for(const sheet of localName(book,'sheet')){
      const id=sheet.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships','id')||sheet.getAttribute('r:id');
      const target=paths.get(id);
      if(!target)continue;
      const doc=await readXml(target.startsWith('/')?target.slice(1):'xl/'+target);
      if(!doc)continue;
      let cols;
      for(const row of localName(doc,'row')){
        const values=cells(row,shared);
        const header=columns(values);
        if(header){cols=header;recognized=true;continue;}
        if(!cols)continue;
        const stamp=excelDate(values[cols.date],epoch);
        const original=String(values[cols.description]??'').trim();
        if(!stamp||!original)continue;
        const currency=words(values[cols.currency]);
        if(currency&&!['uah','грн','980','₴','гривня'].includes(currency)){skipped++;continue;}
        const debit=number(values[cols.debit]),credit=number(values[cols.credit]);
        let amount=debit || credit ? (credit||0)-Math.abs(debit||0) : number(values[cols.amount]);
        const direction=words(values[cols.direction]);
        if(amount&&/списан|витрат|расход|debit/.test(direction))amount=-Math.abs(amount);
        if(amount&&/зарахув|надход|приход|доход|credit/.test(direction))amount=Math.abs(amount);
        if(!amount){skipped++;continue;}
        const time=String(values[cols.time]??'').trim();
        if(/^\d{1,2}:\d{2}(?::\d{2})?$/.test(time))stamp.time=time;
        const card=words(values[cols.card]).replace(/[\s-]/g,'').replace(/[xх•]/g,'*');
        parsed.push({...stamp,amount,original,card,bankId:String(values[cols.bankId]??'').trim(),
          merchant:String(values[cols.merchant]??'').trim()});
      }
    }
    if(!recognized||!parsed.length)throw new Error('В .xlsx не найдены операции с датой, описанием и суммой в гривнах.');
    return {rows:parsed,skipped};
  }

  const escape = value => String(value ?? '').replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g,'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
  async function write(sheets){
    const zip=new JSZip();
    const header='<?xml version="1.0" encoding="UTF-8"?>';
    const ns='http://schemas.openxmlformats.org';
    const sheetType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml';
    const rel=(id,type,target)=>'<Relationship Id="rId'+id+'" Type="'+ns+'/officeDocument/2006/relationships/'+type+'" Target="'+target+'"/>';
    const relationships=rows=>header+'<Relationships xmlns="'+ns+'/package/2006/relationships">'+rows.join('')+'</Relationships>';
    zip.file('[Content_Types].xml',header+'<Types xmlns="'+ns+'/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'+sheets.map((_,i)=>'<Override PartName="/xl/worksheets/sheet'+(i+1)+'.xml" ContentType="'+sheetType+'"/>').join('')+'</Types>');
    zip.file('_rels/.rels',relationships([rel(1,'officeDocument','xl/workbook.xml')]));
    zip.file('xl/workbook.xml',header+'<workbook xmlns="'+ns+'/spreadsheetml/2006/main" xmlns:r="'+ns+'/officeDocument/2006/relationships"><sheets>'+sheets.map(({name},i)=>'<sheet name="'+escape(name)+'" sheetId="'+(i+1)+'" r:id="rId'+(i+1)+'"/>').join('')+'</sheets></workbook>');
    zip.file('xl/_rels/workbook.xml.rels',relationships(sheets.map((_,i)=>rel(i+1,'worksheet','worksheets/sheet'+(i+1)+'.xml'))));
    sheets.forEach(({rows},i)=>{
      const data=rows.map((row,j)=>'<row r="'+(j+1)+'">'+row.map(value=>typeof value==='number'?'<c><v>'+value+'</v></c>':'<c t="inlineStr"><is><t xml:space="preserve">'+escape(value)+'</t></is></c>').join('')+'</row>').join('');
      zip.file('xl/worksheets/sheet'+(i+1)+'.xml',header+'<worksheet xmlns="'+ns+'/spreadsheetml/2006/main"><sheetData>'+data+'</sheetData></worksheet>');
    });
    return zip.generateAsync({type:'blob',compression:'DEFLATE',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
  }
  return {read,write,words,number};
})();