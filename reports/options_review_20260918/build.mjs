import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const out=new URL('.',import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1');
const d=JSON.parse(await fs.readFile(new URL('analysis.json',import.meta.url),'utf8'));
const wb=Workbook.create();
const names=['Overview','Daily volatility','IV history','Strategies','Option source','Model inputs'];
const sheets=Object.fromEntries(names.map(n=>[n,wb.worksheets.add(n)]));
const C={navy:'#18334D',blue:'#34699A',pale:'#EAF0F5',amber:'#FFF0D0',red:'#A33131'};
const money='#,##0.00;(#,##0.00);"–"';
function col(n){let s='';for(n++;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;}
function val(s,cell,v){s.getRange(cell).values=[[v??null]];}
function form(s,cell,f){s.getRange(cell).formulas=[[f]];}
function base(s,title,end,rows){s.showGridLines=false;s.getRange(`A1:${end}${rows}`).format.font={name:'Arial',size:10,color:C.navy};s.getRange(`A1:${end}${rows}`).format.rowHeight=21;s.getRange(`A1:${end}${rows}`).format.columnWidth=15;val(s,'A2',title);s.getRange('A2').format.font={size:16,bold:true};s.getRange(`A3:${end}3`).format.borders={bottom:{style:'thin',color:C.blue}};}
function header(s,row,labels){const r=s.getRange(`A${row}:${col(labels.length-1)}${row}`);r.values=[labels];r.format={fill:C.navy,font:{color:'#FFFFFF',bold:true},wrapText:true,rowHeight:40,verticalAlignment:'center',horizontalAlignment:'center'};}
function table(s,row,n,labels,name){header(s,row,labels);s.tables.add(`A${row}:${col(labels.length-1)}${row+n}`,true,name);s.freezePanes.freezeRows(row);}
function note(s,row,text){val(s,`A${row}`,text);s.getRange(`A${row}`).format.font={color:'#56677A',italic:true};}
function chart(s,ranges,title,start,end,percent=false){let ch=s.charts.add('line',ranges);ch.title=title;ch.setPosition(start,end);ch.titleTextStyle.typeface='Arial';ch.titleTextStyle.fontSize=13;ch.legend={position:'bottom',textStyle:{typeface:'Arial',fontSize:10}};ch.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:10}};ch.yAxis={numberFormatCode:percent?'0%':'#,##0',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:10}};ch.series.items.forEach((x,i)=>x.line={fill:[C.blue,'#C67B37','#719886'][i%3],width:2,style:'solid'});return ch;}
// Original observations, unchanged. Formula-derived close preserved as text evidence.
let s=sheets['Option source'];base(s,'Original PPI option observations','L',d.rows.length+6);
note(s,4,'Source: options_data.xlsx / Sheet1. The added Closing price column is not used in the analysis.');
const rh=['Session date','price (PPI)','volume (PPI)','openingPrice','Closing price (cached)','max','min','previousClose','marketChange','marketChangePercent','ticker','Closing price formula'];
s.getRange(`A7:L${d.rows.length+6}`).values=d.rows.map(x=>[new Date(x.date+'T00:00:00Z'),...x.raw.slice(1),"'"+x.close_formula]);
note(s,5,'Session date preserves the calendar date of the original PPI timestamp (UTC−03:00).');s.getRange('A7:A926').setNumberFormat('dd-mmm-yyyy');
table(s,6,d.rows.length,rh,'SourceOptions');s.getRange(`B7:J${d.rows.length+6}`).setNumberFormat(money);s.getRange('A1:A926').format.columnWidth=31;s.getRange('K1:L926').format.columnWidth=24;
// Model assumptions and complete stock warm-up series.
s=sheets['Model inputs'];base(s,'Inputs and interpretation','H',125);s.getRange('A1:A125').format.columnWidth=28;s.getRange('B1:H125').format.columnWidth=17;
const notes=[
 ['Expiry',new Date('2026-10-16T00:00:00Z'),'Matched to saved BYMA September 7 option metadata.'],
 ['Rate used',.30,'30% annual continuous rate, illustrative constant; not an observed funding curve.'],
 ['Dividend yield used',0,'q = 0 assumption; no verified forward dividend schedule.'],
 ['Shares per contract',100,'Standard BYMA share-option lot. Check extraordinary corporate adjustments.'],
 ['Day-count basis',365,'Actual calendar days / 365.'],
 ['Annualization sessions',252,'Realized volatility uses sample standard deviation of daily log returns.'],
 ['Low/high rate checks','20% / 40%','Illustrative rate sensitivity; same model, spot and option price.'],
 ['Call IV engine','Black-Scholes, q=0','Equivalent to American call under the stated non-dividend assumption.'],
 ['Put IV engine','American CRR, 200 steps','29 bisections, bounded 0–500% IV; rejects unstable/intrinsic-bound prices.'],
 ['Strike mapping','Numeric ticker strike','No security-master strike adjustments verified. All outputs conditional on this mapping.'],
 ['Price basis','PPI price as reported','No use of next-row opening price as a close. No bid/ask spread information.'],
 ['Volume basis','Unverified raw field','P/C raw-volume ratio is NOT a verified contract-count ratio. May be monetary turnover.'],
 ['IV screening','Volume > 0; price in range','Also rejects below-intrinsic prices and model-bound violations. Not proof of a fresh quote.'],
 ['IV / Greeks refresh','Externally calculated snapshot','Re-run analysis after changing inputs. Editing assumptions here does not recompute IV.'],
 ['Delta / vega','European BS diagnostics','Using estimated IV. Vega is ARS per share per 1 percentage-point IV change.'],
 ['ATM series','Nearest paired strike within 8%','Average call/put IV at that strike. Strike can change; tenor declines. Not constant maturity.'],
 ['25-delta skew','Put IV minus call IV','Linear interpolation by BS delta, no extrapolation. American-put delta is approximated.'],
 ['Volatility butterfly','(25d call + 25d put)/2 − ATM','Smile curvature, distinct from the 1:-2:1 price strategy.'],
 ['RV / IV comparison','Diagnostic only','Backward RV and forward IV cover different periods; gap is not guaranteed excess return.'],
 ['Strategy P&L','Expiration, ARS per share','Excludes fees, financing, slippage and early-assignment cash flows. Multiply by 100 per standard set.'],
 ['1x2 call risk','Unlimited upside loss','One long lower-strike call and two short higher-strike calls.'],
 ['1x2 put risk','Large downside loss','One long higher-strike put and two short lower-strike puts. Downside bound assumes spot >= 0.'],
 ['Missing measures','OI / bid-ask / term structure','No OI, quotes or second expiry. No full-year IV rank or percentile from 19 days.'],
 ['Sources','PPI API and user workbook','Stock: MarketData/Search, GGAL, ACCIONES, A-24HS, June 1–September 16, 2026.'],
 ['BYMA contract rules','https://www.byma.com.ar/productos/productos-financieros/opciones','American exercise, standard lot and corporate-action policy.'],
 ['Butterfly reference','https://www.optionseducation.org/strategies/all-strategies/long-call-butterfly','Payoff and expiration characteristics.'],
 ['Ratio reference','https://www.optionseducation.org/strategies/all-strategies/short-ratio-call-spread','1x2 call exposure and risk.']
];
notes.forEach((r,i)=>{val(s,`A${5+i}`,r[0]);val(s,`B${5+i}`,r[1]);val(s,`D${5+i}`,r[2]);});
for(let row=29;row<=31;row++){val(s,`B${row}`,null);val(s,`D${row}`,notes[row-5][1]);}
s.getRange('B5').setNumberFormat('dd-mmm-yy');s.getRange('B6:B7').setNumberFormat('0.0%');s.getRange('B5:B18').format.font.color='#2458A4';
header(s,35,['Date','GGAL price','Open','High','Low','Raw volume']);s.getRange(`A36:F${35+d.stock.length}`).values=d.stock.map(x=>[new Date(x.date.slice(0,10)+'T00:00:00Z'),x.price,x.openingPrice,x.max,x.min,x.volume]);s.getRange(`A36:A${35+d.stock.length}`).setNumberFormat('dd-mmm-yy');s.getRange(`B36:F${35+d.stock.length}`).setNumberFormat(money);
// Contract-level historical analytics.
s=sheets['IV history'];base(s,'Historical implied volatility estimates','R',926);note(s,4,'Model snapshot: 30% rate, zero dividends. Conditional on ticker strikes and PPI prices. See Model inputs.');
const ih=['Date','Ticker','Type','Strike','PPI price','GGAL spot','Days to expiry','Intrinsic','Time value','K / spot','IV estimate','BS delta','BS vega / 1pp','Raw volume','Low','High','Data status','Source row'];
table(s,6,d.rows.length,ih,'HistoricalIV');
const ivrows=[...d.rows].sort((a,b)=>b.date.localeCompare(a.date)||Math.abs(a.k-a.s)-Math.abs(b.k-b.s)||a.side.localeCompare(b.side));
s.getRange('A7:R926').values=ivrows.map(x=>[new Date(x.date+'T00:00:00Z'),x.ticker,x.side,x.k,null,x.s,x.dte,null,null,null,x.iv,x.delta,x.vega,null,null,null,x.status,x.row]);
ivrows.forEach((x,i)=>{let r=i+7,z=x.row+5;form(s,`E${r}`,`='Option source'!B${z}`);form(s,`N${r}`,`='Option source'!C${z}`);form(s,`O${r}`,`='Option source'!G${z}`);form(s,`P${r}`,`='Option source'!F${z}`);form(s,`H${r}`,`=MAX(IF(C${r}="call",F${r}-D${r},D${r}-F${r}),0)`);form(s,`I${r}`,`=E${r}-H${r}`);form(s,`J${r}`,`=D${r}/F${r}`);});
s.getRange('A7:A926').setNumberFormat('dd-mmm-yy');s.getRange('D7:I926').setNumberFormat(money);s.getRange('J7:K926').setNumberFormat('0.0%');s.getRange('L7:M926').setNumberFormat('0.000');s.getRange('N7:P926').setNumberFormat(money);s.getRange('B1:B926').format.columnWidth=21;s.getRange('Q1:Q926').format.columnWidth=65;
s.getRange('G7:G926').setNumberFormat('0');s.getRange('Q7:Q926').conditionalFormats.add('notContainsText',{text:'Screen passed',format:{fill:C.amber,font:{color:C.red}}});
// Daily market measures with formula-derived comparisons.
s=sheets['Daily volatility'];base(s,'Daily volatility and market ratios','V',28);note(s,4,'P/C volume uses the raw API field. IV uses the same October expiry each day, not a constant-maturity series.');
const dh=['Date','GGAL spot','ATM strike','Call IV','Put IV','ATM IV avg','RV 10d','RV 20d','RV 60d','IV − RV20','IV / RV20','P/C IV','Call raw volume','Put raw volume','P/C raw volume','25d call IV','25d put IV','25d skew','Vol butterfly','IV at 20% rate','IV at 40% rate','Valid IV rows'];
table(s,6,d.daily.length,dh,'DailyMeasures');
s.getRange(`A7:V${6+d.daily.length}`).values=d.daily.map(x=>[new Date(x.date+'T00:00:00Z'),x.s,x.k,x.call_iv,x.put_iv,x.atm,x.rv10,x.rv20,x.rv60,null,null,null,null,null,null,x.call25,x.put25,null,null,x.r20,x.r40,x.valid]);
d.daily.forEach((x,i)=>{let r=i+7;for(let [c,f] of Object.entries({J:`=IF(F${r}="","n.a.",F${r}-H${r})`,K:`=IF(F${r}="","n.a.",F${r}/H${r})`,L:`=IF(D${r}="","n.a.",E${r}/D${r})`,M:`=SUMIFS('IV history'!$N$7:$N$926,'IV history'!$A$7:$A$926,A${r},'IV history'!$C$7:$C$926,"call")`,N:`=SUMIFS('IV history'!$N$7:$N$926,'IV history'!$A$7:$A$926,A${r},'IV history'!$C$7:$C$926,"put")`,O:`=IF(M${r}=0,"n.a.",N${r}/M${r})`,R:`=IF(OR(P${r}="",Q${r}=""),"n.a.",Q${r}-P${r})`,S:`=IF(OR(P${r}="",Q${r}="",F${r}=""),"n.a.",(P${r}+Q${r})/2-F${r})`}))form(s,`${c}${r}`,f);});
s.getRange('A7:A25').setNumberFormat('dd-mmm-yy');s.getRange('B7:C25').setNumberFormat(money);s.getRange('D7:J25').setNumberFormat('0.0%');s.getRange('K7:L25').setNumberFormat('0.00"x"');s.getRange('M7:N25').setNumberFormat('#,##0');s.getRange('O7:O25').setNumberFormat('0.00"x"');s.getRange('P7:U25').setNumberFormat('0.0%');
// All dated spread constructions, most recent first; arithmetic remains editable.
s=sheets['Strategies'];const spotByDay=Object.fromEntries(d.daily.map(x=>[x.date,x.s]));const spreads=d.spreads.sort((a,b)=>b.date.localeCompare(a.date)||b.type.localeCompare(a.type)||(a.status==='Indicative only'?0:1)-(b.status==='Indicative only'?0:1)||Math.abs(a.k2-spotByDay[a.date])-Math.abs(b.k2-spotByDay[b.date])||a.side.localeCompare(b.side));base(s,'Butterflies and 1x2 ratio spreads','T',spreads.length+6);
note(s,4,'Indicative PPI prices only. Expiration P&L excludes costs and early assignment. 1x2 calls have unlimited upside loss.');
const sh=['Date','Strategy','Type','Long strike 1','Short strike 2 (x2)','Long strike 3','Premium 1','Premium 2','Premium 3','Net debit / share','Strike width','Peak P&L / share','Max loss / share','Lower breakeven','Upper breakeven','Peak / debit','Net debit / set','Data status','Long leg source','Short leg source'];
table(s,6,spreads.length,sh,'SpreadHistory');
s.getRange(`A7:T${spreads.length+6}`).values=spreads.map(x=>[new Date(x.date+'T00:00:00Z'),x.type,x.side,x.k1,x.k2,x.k3,null,null,null,null,null,null,null,null,null,null,null,x.status,x.row1,x.row2]);
spreads.forEach((x,i)=>{let r=i+7;form(s,`G${r}`,`='Option source'!B${x.row1+5}`);form(s,`H${r}`,`='Option source'!B${x.row2+5}`);if(x.row3)form(s,`I${r}`,`='Option source'!B${x.row3+5}`);form(s,`J${r}`,`=G${r}-2*H${r}+IF(B${r}="Butterfly",I${r},0)`);form(s,`K${r}`,`=ABS(E${r}-D${r})`);form(s,`L${r}`,`=K${r}-J${r}`);form(s,`M${r}`,`=IF(B${r}="Butterfly",MAX(J${r},0),IF(C${r}="call","Unlimited",MAX(2*E${r}-D${r}+J${r},J${r},0)))`);form(s,`N${r}`,`=IF(B${r}="Butterfly",IF(AND(J${r}>0,J${r}<K${r}),D${r}+J${r},"n.a."),IF(C${r}="call",IF(AND(J${r}>0,J${r}<K${r}),D${r}+J${r},"n.a."),IF(AND(K${r}>J${r},2*E${r}-D${r}+J${r}>=0),2*E${r}-D${r}+J${r},"n.a.")))`);form(s,`O${r}`,`=IF(B${r}="Butterfly",IF(AND(J${r}>0,J${r}<K${r}),F${r}-J${r},"n.a."),IF(C${r}="call",IF(K${r}>J${r},2*E${r}-D${r}-J${r},"n.a."),IF(AND(J${r}>0,J${r}<K${r}),D${r}-J${r},"n.a.")))`);form(s,`P${r}`,`=IF(AND(B${r}="Butterfly",J${r}>0,J${r}<K${r}),L${r}/J${r},"n.a.")`);form(s,`Q${r}`,`=J${r}*'Model inputs'!$B$8`);});
s.getRange(`A7:A${spreads.length+6}`).setNumberFormat('dd-mmm-yy');s.getRange(`D7:Q${spreads.length+6}`).setNumberFormat(money);s.getRange(`P7:P${spreads.length+6}`).setNumberFormat('0.00"x"');s.getRange(`R1:R${spreads.length+6}`).format.columnWidth=38;s.getRange(`R7:R${spreads.length+6}`).conditionalFormats.add('notContainsText',{text:'Indicative only',format:{fill:C.amber,font:{color:C.red}}});
// Concise primary view and useful charts.
s=sheets.Overview;base(s,'Galicia options: what the data says','L',64);s.tabColor=C.navy;s.getRange('A1:A64').format.columnWidth=27;s.getRange('B1:B64').format.columnWidth=20;s.getRange('C1:L64').format.columnWidth=13;
note(s,4,'21 Aug–16 Sep 2026. October expiry. ARS per share unless stated. Historical estimates, not executable quotes.');
header(s,6,['Latest date','GGAL spot','ATM strike','ATM IV','20-day RV','IV / RV20']);
['A','B','C','F','H','K'].forEach((c,i)=>form(s,`${col(i)}7`,`='Daily volatility'!${c}25`));s.getRange('A7').setNumberFormat('dd-mmm-yy');s.getRange('B7:C7').setNumberFormat(money);s.getRange('D7:E7').setNumberFormat('0.0%');s.getRange('F7').setNumberFormat('0.00"x"');s.getRange('A7:F7').format.rowHeight=32;s.getRange('A7:F7').format.font.bold=true;
const findings=[
 ['Coverage',`${d.rows.length} observations, 50 series, 19 dates. Calls and puts share one expiry.`],
 ['Closing-price problem','The added Closing price column refers to next-row openingPrice. It is excluded.'],
 ['Data screening',`${d.rows.filter(x=>x.iv!==null).length} IV estimates retained. Zero-volume and inconsistent-range rows are excluded.`],
 ['Model uncertainty','30% continuous rate and zero dividends are assumptions. Daily table includes 20% / 40% rate checks.'],
 ['Put/call ratio','Raw-volume ratio measures this file only. Volume units and market-wide coverage are unverified.'],
 ['Strategy use','Compare historical costs and payoff shapes. Negative butterfly costs are data flags, not proven arbitrage.'],
 ['Missing context','No bid/ask, OI or second expiry. Nineteen dates cannot support a 1-year IV rank.']
];
findings.forEach((x,i)=>{val(s,`A${10+i}`,x[0]);val(s,`B${10+i}`,x[1]);s.getRange(`A${10+i}`).format.font.bold=true;});
header(s,20,['Date','ATM IV','20-day RV']);
d.daily.forEach((x,i)=>{let r=21+i,z=7+i;form(s,`A${r}`,`=TEXT('Daily volatility'!A${z},"dd-mmm")`);form(s,`B${r}`,`='Daily volatility'!F${z}`);form(s,`C${r}`,`='Daily volatility'!H${z}`);});s.getRange('B21:C39').setNumberFormat('0.0%');chart(s,s.getRange('A20:C39'),'Estimated IV and realized volatility','E20','L39',true);
header(s,43,['Quality check','Count']);const q=[['Zero reported volume',d.counts['Zero reported volume']],['Price outside range',d.counts['Price outside daily range']],['Below intrinsic',d.counts['Below intrinsic value']],['Model-bound failure',d.counts['No stable model IV']],['Duplicate date / ticker',0]];s.getRange('A44:B48').values=q;note(s,50,'Quality counts overlap. Screened prices can still be stale or asynchronous.');
val(s,'A53','How to read the measures');val(s,'A55','IV vs. RV');val(s,'B55','IV describes model-implied future uncertainty; RV measures past share-price variability.');val(s,'A57','Butterfly');val(s,'B57','Buy the two wings and sell two middle-strike options. Peak expiration P&L is at the middle strike.');val(s,'A59','1x2 ratio');val(s,'B59','Buy one option and sell two further out-of-the-money options. Premium income adds tail exposure.');
const example=spreads.findIndex(x=>x.date===d.latest&&x.type==='Butterfly'&&x.side==='call'&&x.k2===6800)+7;
s.getRange('A65:L95').format.font={name:'Arial',size:10,color:C.navy};s.getRange('A65:L95').format.rowHeight=21;
val(s,'A65','Example: 6,600 / 6,800 / 7,000 call butterfly');s.getRange('A65').format.font.bold=true;
note(s,66,'16 Sep prices. Buy 1 call at 6,600, sell 2 at 6,800, buy 1 at 7,000. All expiration outcomes exclude costs.');
header(s,68,['Debit / share','Max profit / share','Max loss / share','Lower breakeven','Upper breakeven','Debit / 100 shares']);
['J','L','M','N','O','Q'].forEach((c,i)=>form(s,`${col(i)}69`,`='Strategies'!${c}${example}`));s.getRange('A69:F69').setNumberFormat(money);
header(s,72,['GGAL at expiry','P&L / share']);
for(let i=0;i<=24;i++){let r=73+i;val(s,`A${r}`,6200+i*50);form(s,`B${r}`,`=MAX(A${r}-'Strategies'!D${example},0)-2*MAX(A${r}-'Strategies'!E${example},0)+MAX(A${r}-'Strategies'!F${example},0)-$A$69`);}
s.getRange('A73:B97').setNumberFormat(money);chart(s,s.getRange('A72:B97'),'Butterfly expiration payoff (ARS per share)','E72','L98',false);
// Verify live strategy arithmetic responds to a real premium change, then restore.
const sourceCell=sheets['Option source'].getRange(`B${spreads[example-7].row1+5}`);
const original=sourceCell.values[0][0],oldDebit=s.getRange('A69').values[0][0];
sourceCell.values=[[original+1]];
if(Math.abs(s.getRange('A69').values[0][0]-oldDebit-1)>1e-7)throw Error('Strategy recalculation failed');
sourceCell.values=[[original]];
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Overview!A6:F7',include:'values,formulas',tableMaxRows:3,tableMaxCols:6})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:15},summary:'Formula check'})).ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(fileURLToPath(new URL('Galicia_options_analysis.xlsx',import.meta.url)));
for(const [name,range] of [['Overview','A1:L39'],['Daily volatility','A1:L12'],['IV history','A1:R12'],['Strategies','A1:T12'],['Option source','A1:L12'],['Model inputs','A1:J32']]){
 try{const img=await wb.render({sheetName:name,range,scale:1,format:'png'});await fs.writeFile(new URL(name.replaceAll(' ','_')+'.png',import.meta.url),new Uint8Array(await img.arrayBuffer()));console.log('Rendered',name);}catch(e){console.log('Render failure',name,e.message);}
}
const payoff=await wb.render({sheetName:'Overview',range:'A65:L99',scale:1,format:'png'});await fs.writeFile(new URL('payoff.png',import.meta.url),new Uint8Array(await payoff.arrayBuffer()));
