import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {Workbook,SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const dir=new URL('.',import.meta.url);
const target=new URL('Galicia_options_analysis.xlsx',dir);
const backup=new URL('before_ratio.xlsx',dir);
try{await fs.access(backup);}catch{await fs.copyFile(target,backup);}
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(fileURLToPath(backup)));
console.log((await wb.inspect({kind:'table',range:'IV history!A6:G8',include:'values,formulas',tableMaxRows:3,tableMaxCols:7})).ndjson);
const data=JSON.parse(await fs.readFile(new URL('analysis.json',dir),'utf8'));
const s=wb.worksheets.add('Ratio explorer');
const navy='#18334D',blue='#34699A',orange='#C67B37',amber='#FFF0D0';
const money='#,##0.00;(#,##0.00);"–"';
const v=(c,x)=>s.getRange(c).values=[[x]];
const f=(c,x)=>s.getRange(c).formulas=[[x]];
s.showGridLines=false;s.tabColor=blue;
s.getRange('A1:N59').format={font:{name:'Arial',size:10,color:navy},rowHeight:22,columnWidth:13,verticalAlignment:'center'};
s.getRange('A1:A59').format.columnWidth=22;s.getRange('B1:B59').format.columnWidth=18;
s.getRange('I1:J59').format.columnWidth=24;
v('A2','Ratio explorer');s.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:navy};
s.getRange('A3:N3').format.borders={bottom:{style:'thin',color:blue}};
v('A4','Change the four amber cells. Buy one option at the long strike and sell the chosen quantity at the short strike.');
s.getRange('A4').format.font.italic=true;
[['Option type','call'],['Long strike',6800],['Short strike',7000],['Long : short ratio','1:2']].forEach((x,i)=>{v(`A${i+6}`,x[0]);v(`B${i+6}`,x[1]);});
s.getRange('B6:B9').format={fill:amber,font:{color:'#2458A4',bold:true},horizontalAlignment:'center'};
s.getRange('B6').setNumberFormat('@');s.getRange('B9').setNumberFormat('@');
s.getRange('B7:B8').setNumberFormat('#,##0');
v('A10','Short quantity');f('B10','=IF(B9="1:1",1,IF(B9="1:2",2,""))');
v('A11','Shares per contract');f('B11',"='Model inputs'!B8");
v('A12','Expiry');f('B12',"='Model inputs'!B5");s.getRange('B12').setNumberFormat('dd-mmm-yyyy');
v('P3','Selection lists');v('P5','Call strikes');v('Q5','Put strikes');
const cs=[...new Set(data.rows.filter(x=>x.side==='call').map(x=>x.k))].sort((a,b)=>a-b);
const ps=[...new Set(data.rows.filter(x=>x.side==='put').map(x=>x.k))].sort((a,b)=>a-b);
s.getRange(`P6:P${5+cs.length}`).values=cs.map(x=>[x]);s.getRange(`Q6:Q${5+ps.length}`).values=ps.map(x=>[x]);
s.getRange('B6').dataValidation={rule:{type:'list',values:['call','put']}};
s.getRange('B7:B8').dataValidation={rule:{type:'list',formula1:'IF($B$6="call",$P$6:$P$31,$Q$6:$Q$29)'}};
s.getRange('B9').dataValidation={rule:{type:'list',values:['1:1','1:2']}};
f('D6','=IF(OR(B6="",B7="",B8="",B9=""),"Choose all four inputs",IF(AND(B6<>"call",B6<>"put"),"Choose call or put",IF(AND(B9<>"1:1",B9<>"1:2"),"Choose 1:1 or 1:2",IF(OR(NOT(ISNUMBER(B7)),NOT(ISNUMBER(B8))),"Choose numeric strikes",IF(B7=B8,"Choose two different strikes",IF(OR(COUNTIFS(\'IV history\'!$C$7:$C$926,B6,\'IV history\'!$D$7:$D$926,B7)=0,COUNTIFS(\'IV history\'!$C$7:$C$926,B6,\'IV history\'!$D$7:$D$926,B8)=0),"Strike unavailable for this type","Ready"))))))');
s.getRange('D6').format.font.bold=true;
s.getRange('D6:G6').conditionalFormats.addCustom('$D$6<>"Ready"',{fill:amber,font:{color:'#A33131',bold:true}});
v('D8','Latest date');f('E8','=A56');s.getRange('E8').setNumberFormat('dd-mmm-yy');
v('G8','Cost / share');f('H8','=IF(ISNUMBER(D56),D56,"n.a.")');s.getRange('H8').setNumberFormat(money);
v('J8','Cost / contract set');f('L8','=IF(ISNUMBER(E56),E56,"n.a.")');s.getRange('L8').setNumberFormat(money);
v('D10','Long-leg IV');f('E10','=IF(ISNUMBER(F56),F56,"n.a.")');v('G10','Short-leg IV');f('H10','=IF(ISNUMBER(G56),G56,"n.a.")');
s.getRange('E10').setNumberFormat('0.0%');s.getRange('H10').setNumberFormat('0.0%');
f('D12','=IF(D6<>"Ready","Select valid contracts to populate the charts.",IF(B9="1:1","1:1 spread: long premium minus short premium.",IF(B6="call","1:2 calls: uncovered upside exposure, with unlimited potential loss.","1:2 puts: substantial downside exposure if GGAL falls.")))');
v('A14','Positive cost = debit. Negative cost = credit. ARS per share, before fees and slippage.');
v('A15','Costs include flagged prices. IV assumptions: 30% rate, zero dividends. Gaps mean unavailable IV.');
s.getRange('A14:A15').format.font={name:'Arial',size:10,color:'#56677A',italic:true};
// Bound presentation notes explicitly so they remain visible beside the controls.
for(const range of ['D12:N12','A14:N14','A15:N15']){s.mergeCells(range);s.getRange(range).format.wrapText=true;}
const headers=['Date','Long premium','Short premium','Cost / share','Cost / set','Long IV','Short IV','IV gap (pp)','Long data','Short data'];
s.getRange('A37:J37').values=[headers];
s.getRange('A37:J37').format={fill:navy,font:{color:'#FFFFFF',bold:true},rowHeight:36,wrapText:true,horizontalAlignment:'center'};
v('K37','Long rows');v('L37','Short rows');v('M37','Long IV count');v('N37','Short IV count');
v('S37','Date');v('T37','Historical cost');v('U37','Long-leg IV');v('V37','Short-leg IV');
const a="'IV history'!$A$7:$A$926",typ="'IV history'!$C$7:$C$926",strike="'IV history'!$D$7:$D$926",price="'IV history'!$E$7:$E$926",iv="'IV history'!$K$7:$K$926";
for(let i=0;i<19;i++){
 const r=38+i;
 f(`A${r}`,`='Daily volatility'!A${7+i}`);
 const criteria=k=>`${a},A${r},${typ},$B$6,${strike},$B$${k}`;
 f(`K${r}`,`=IF($D$6<>"Ready","",COUNTIFS(${criteria(7)}))`);
 f(`L${r}`,`=IF($D$6<>"Ready","",COUNTIFS(${criteria(8)}))`);
 f(`M${r}`,`=IF(K${r}<>1,"",COUNTIFS(${criteria(7)},${iv},">0"))`);
 f(`N${r}`,`=IF(L${r}<>1,"",COUNTIFS(${criteria(8)},${iv},">0"))`);
 f(`B${r}`,`=IF(K${r}<>1,"",SUMIFS(${price},${criteria(7)}))`);
 f(`C${r}`,`=IF(L${r}<>1,"",SUMIFS(${price},${criteria(8)}))`);
 f(`D${r}`,`=IF(AND(ISNUMBER(B${r}),ISNUMBER(C${r})),B${r}-$B$10*C${r},"")`);
 f(`E${r}`,`=IF(ISNUMBER(D${r}),D${r}*$B$11,"")`);
 f(`F${r}`,`=IF(M${r}<>1,"",SUMIFS(${iv},${criteria(7)}))`);
 f(`G${r}`,`=IF(N${r}<>1,"",SUMIFS(${iv},${criteria(8)}))`);
 f(`H${r}`,`=IF(AND(ISNUMBER(F${r}),ISNUMBER(G${r})),100*(F${r}-G${r}),"")`);
 f(`I${r}`,`=IF($D$6<>"Ready","Check selection",IF(K${r}=0,"No observation",IF(K${r}>1,"Duplicate observations",IF(M${r}=0,"Flagged; IV unavailable","Screen passed"))))`);
 f(`J${r}`,`=IF($D$6<>"Ready","Check selection",IF(L${r}=0,"No observation",IF(L${r}>1,"Duplicate observations",IF(N${r}=0,"Flagged; IV unavailable","Screen passed"))))`);
 f(`S${r}`,`=TEXT(A${r},"dd-mmm")`);
 // Intentional #N/A chart helpers prevent missing observations being plotted as zero.
 for(const [c,src] of [['T','D'],['U','F'],['V','G']])f(`${c}${r}`,`=IF(ISNUMBER(${src}${r}),${src}${r},NA())`);
}
s.getRange('A38:A56').setNumberFormat('dd-mmm-yy');s.getRange('B38:E56').setNumberFormat(money);s.getRange('F38:G56').setNumberFormat('0.0%');s.getRange('H38:H56').setNumberFormat('0.0" pp"');
s.getRange('I38:J56').format.wrapText=true;s.getRange('A38:J56').format.rowHeight=30;
s.getRange('I38:J56').conditionalFormats.add('notContainsText',{text:'Screen passed',format:{fill:amber,font:{color:'#A33131'}}});
v('S34','Chart helpers: #N/A means a deliberate gap, never a zero.');
v('A58','Changing the ratio changes cost, not either leg’s IV. IV gap = long IV minus short IV, in percentage points.');
v('A59','Coverage: 21 Aug–16 Sep 2026. Fixed October expiry. Flags and original observations remain in IV history.');
function makeChart(ranges,title,start,end,pct){
 const c=s.charts.add('line',ranges);c.title=title;c.setPosition(start,end);
 c.titleTextStyle.fontSize=13;c.titleTextStyle.typeface='Arial';
 c.legend={position:'bottom',textStyle:{typeface:'Arial',fontSize:10}};
 c.xAxis={axisType:'textAxis',textStyle:{typeface:'Arial',fontSize:9}};
 c.yAxis={numberFormatCode:pct?'0%':'#,##0.00',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:10}};
 c.series.items.forEach((x,i)=>x.line={fill:i?orange:blue,width:2,style:'solid'});
 return c;
}
makeChart(s.getRange('S37:T56'),'Historical cost (ARS per share)','A17','G35',false);
makeChart([s.getRange('S37:S56'),s.getRange('U37:U56'),s.getRange('V37:V56')],'Historical IV by leg','H17','N35',true);
// Exercise controls against independent calculations over all 19 dates.
const lookup=new Map(data.rows.map(x=>[`${x.date}|${x.side}|${x.k}`,x]));
let checks=0;
function select(type,k1,k2,ratio){v('B6',type);v('B7',k1);v('B8',k2);v('B9',ratio);}
function near(actual,expected,msg){if(Math.abs(actual-expected)>1e-8||typeof actual!=='number')throw Error(msg+': '+actual+' vs '+expected);checks++;}
for(const [type,k1,k2,ratio] of [['call',6800,7000,'1:1'],['call',6800,7000,'1:2'],['put',7000,6600,'1:2'],['put',7000,6800,'1:1'],['call',4800,9900,'1:2']]){
 select(type,k1,k2,ratio);
 for(let i=0;i<19;i++){
  const day=data.daily[i].date,r=38+i;
  const l=lookup.get(`${day}|${type}|${k1}`),sh=lookup.get(`${day}|${type}|${k2}`);
  const values=s.getRange(`B${r}:G${r}`).values[0];
  if(l&&sh){near(values[2],l.p-(ratio==='1:2'?2:1)*sh.p,'Cost');near(values[3],100*values[2],'Contract cost');}
  else if(values[2]!==''&&values[2]!==null)throw Error('Missing observation became a cost');
  for(const [x,j] of [[l,4],[sh,5]]){if(x?.iv)near(values[j],x.iv,'Leg IV');else if(values[j]!==''&&values[j]!==null)throw Error('Missing IV became numeric');}
 }
}
for(const selection of [['call',6800,6800,'1:2'],['put',9900,7000,'1:2'],['call',null,7000,'1:2'],['call',6800,7000,null]]){
 select(...selection);if(s.getRange('D6').values[0][0]==='Ready'||typeof s.getRange('D56').values[0][0]==='number')throw Error('Invalid selection accepted');checks++;
}
select('call',6800,7000,'1:2');
const source=wb.worksheets.getItem('IV history');const saved=source.getRange('C8').values[0][0];source.getRange('C8').values=[['call']];
if(s.getRange('I56').values[0][0]!=='Duplicate observations')throw Error('Duplicate key not detected');
source.getRange('C8').values=[[saved]];
// Zero source premiums remain numeric, rather than being treated as missing.
const src=wb.worksheets.getItem('Option source').getRange('B258'),old=src.values[0][0];src.values=[[0]];near(s.getRange('D56').values[0][0],-2*289.65,'Zero premium');src.values=[[old]];
wb.recalculate();
console.log('Selection and boundary checks passed:',checks);
console.log((await wb.inspect({kind:'table',range:'Ratio explorer!A54:J56',include:'values,formulas',tableMaxRows:3,tableMaxCols:10})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:20},summary:'Unexpected formula errors'})).ndjson);
await (await SpreadsheetFile.exportXlsx(wb)).save(fileURLToPath(target));
for(const [range,name] of [['A1:N35','ratio_controls.png'],['A37:J59','ratio_history.png']]){
 const image=await wb.render({sheetName:'Ratio explorer',range,scale:1,format:'png'});await fs.writeFile(new URL(name,dir),new Uint8Array(await image.arrayBuffer()));
}
console.log('Saved updated workbook');
