import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {SpreadsheetFile,FileBlob} from '@oai/artifact-tool';
const dir=new URL('.',import.meta.url),target=new URL('Galicia_options_analysis.xlsx',dir),backup=new URL('before_iv_curve.xlsx',dir);
try{await fs.access(backup);}catch{await fs.copyFile(target,backup);}
const wb=await SpreadsheetFile.importXlsx(await FileBlob.load(fileURLToPath(backup)));
const data=JSON.parse(await fs.readFile(new URL('analysis.json',dir),'utf8'));
const s=wb.worksheets.add('IV curve explorer');
const navy='#18334D',blue='#34699A',orange='#C67B37',amber='#FFF0D0';
const v=(c,x)=>s.getRange(c).values=[[x]],f=(c,x)=>s.getRange(c).formulas=[[x]];
const col=n=>{let x='';for(n++;n;n=Math.floor((n-1)/26))x=String.fromCharCode(65+(n-1)%26)+x;return x;};
s.showGridLines=false;s.tabColor=blue;
s.getRange('A1:T100').format={font:{name:'Arial',size:10,color:navy},rowHeight:22,columnWidth:13,verticalAlignment:'center'};
s.getRange('A1:A100').format.columnWidth=24;s.getRange('B1:B100').format.columnWidth=17;
s.getRange('E1:F65').format.columnWidth=20;
v('A2','IV curve explorer');s.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:navy};s.getRange('A3:N3').format.borders={bottom:{style:'thin',color:blue}};
v('A4','Choose a reference session, then move forward or backward using the session-step control.');
[['Option type','call'],['Reference day',new Date('2026-09-01T00:00:00Z')],['Sessions forward / back',1],['Comparison day',null],['Watch one strike',6800]].forEach((x,i)=>{v(`A${6+i}`,x[0]);if(x[1]!==null)v(`B${6+i}`,x[1]);});
s.getRange('B6:B8').format={fill:amber,font:{color:'#2458A4',bold:true},horizontalAlignment:'center'};s.getRange('B10').format={fill:amber,font:{color:'#2458A4',bold:true},horizontalAlignment:'center'};
s.getRange('B6').setNumberFormat('@');s.getRange('B7').setNumberFormat('dd-mmm-yyyy');s.getRange('B8').setNumberFormat('+0;-0;0');s.getRange('B9').setNumberFormat('dd-mmm-yyyy');s.getRange('B10').setNumberFormat('#,##0');
v('A11','Expiry');f('B11',"='Model inputs'!B5");s.getRange('B11').setNumberFormat('dd-mmm-yyyy');
v('AD4','Dropdown lists');v('AD5','Available dates');v('AE5','Call strikes');v('AF5','Put strikes');v('AG5','Session steps');
const cs=[...new Set(data.rows.filter(x=>x.side==='call').map(x=>x.k))].sort((a,b)=>a-b),ps=[...new Set(data.rows.filter(x=>x.side==='put').map(x=>x.k))].sort((a,b)=>a-b);
for(let i=0;i<19;i++)f(`AD${6+i}`,`='Daily volatility'!A${7+i}`);
s.getRange('AD6:AD24').setNumberFormat('dd-mmm-yyyy');s.getRange('AE6:AE31').values=cs.map(x=>[x]);s.getRange('AF6:AF29').values=ps.map(x=>[x]);s.getRange('AG6:AG42').values=Array.from({length:37},(_,i)=>[i-18]);
s.getRange('B6').dataValidation={rule:{type:'list',values:['call','put']}};s.getRange('B7').dataValidation={rule:{type:'list',formula1:'$AD$6:$AD$24'}};s.getRange('B8').dataValidation={rule:{type:'list',formula1:'$AG$6:$AG$42'}};s.getRange('B10').dataValidation={rule:{type:'list',formula1:'IF($B$6="call",$AE$6:$AE$31,$AF$6:$AF$29)'}};
f('D6','=IF(AND(B6<>"call",B6<>"put"),"Choose call or put",IF(COUNTIFS($AD$6:$AD$24,B7)<>1,"Choose an available reference day",IF(NOT(ISNUMBER(B8)),"Choose a whole-number session step",IF(B8<>INT(B8),"Choose a whole-number session step",IF(OR(MATCH(B7,$AD$6:$AD$24,0)+B8<1,MATCH(B7,$AD$6:$AD$24,0)+B8>19),"Step is outside the available history","Ready")))))');
s.mergeCells('D6:N6');s.getRange('D6:N6').format.font.bold=true;
f('B9','=IF(D6="Ready",INDEX($AD$6:$AD$24,MATCH(B7,$AD$6:$AD$24,0)+B8),"")');
v('D8','Reference curve');f('F8','=IF(D6="Ready",B7,"")');v('H8','Comparison curve');f('K8','=IF(D6="Ready",B9,"")');s.getRange('F8').setNumberFormat('dd-mmm-yy');s.getRange('K8').setNumberFormat('dd-mmm-yy');
v('D10','Reference spot');f('F10','=IF(D6="Ready",INDEX(\'Daily volatility\'!$B$7:$B$25,MATCH(B7,$AD$6:$AD$24,0)),"")');v('H10','Comparison spot');f('K10','=IF(D6="Ready",INDEX(\'Daily volatility\'!$B$7:$B$25,MATCH(B9,$AD$6:$AD$24,0)),"")');s.getRange('F10').setNumberFormat('#,##0.00');s.getRange('K10').setNumberFormat('#,##0.00');
v('A13','+1 = next available session; -1 = previous session. Change the step to move through time while keeping the reference fixed.');
v('A14','Only screened IV estimates are plotted. Missing or excluded observations stay blank; no interpolation or replacement with zero.');
v('A15','Fixed October expiry: days to expiry decline over time. Model assumptions remain 30% annual rate and zero dividends.');
for(const r of [4,13,14,15]){s.mergeCells(`A${r}:N${r}`);s.getRange(`A${r}:N${r}`).format.wrapText=true;}
s.getRange('A13:N15').format.font={name:'Arial',size:10,color:'#56677A',italic:true};
function header(range,values){s.getRange(range).values=[values];s.getRange(range).format={fill:navy,font:{color:'#FFFFFF',bold:true},rowHeight:38,wrapText:true,horizontalAlignment:'center'};}
// This grid owns the retrieval of screened historical IV for the selected option type.
v('A68','Daily IV across strikes');s.getRange('A68').format.font.bold=true;
v('A69','Read down a date to see its curve, or across a strike to see its history. Heatmap colors use the displayed grid range.');s.mergeCells('A69:T69');
header('A71:T71',['Strike',...data.daily.map(x=>new Date(x.date+'T00:00:00Z'))]);s.getRange('B71:T71').setNumberFormat('dd-mmm');
const da="'IV history'!$A$7:$A$926",ty="'IV history'!$C$7:$C$926",st="'IV history'!$D$7:$D$926",iv="'IV history'!$K$7:$K$926";
for(let i=0;i<26;i++){
 const r=72+i;v(`A${r}`,cs[i]);
 for(let j=0;j<19;j++){
  const c=col(j+1),criteria=`${da},${c}$71,${ty},$B$6,${st},$A${r}`;
  f(`${c}${r}`,`=IF(AND(COUNTIFS(${criteria})=1,COUNTIFS(${criteria},${iv},">0")=1),SUMIFS(${iv},${criteria}),"")`);
 }
}
s.getRange('A72:A97').setNumberFormat('#,##0');s.getRange('B72:T97').setNumberFormat('0.0%');s.getRange('B72:T97').conditionalFormats.add('colorScale',{colors:['#F4F7FA','#C1D4E4','#34699A'],thresholds:['min',{type:'percentile',value:50},'max']});
header('A38:F38',['Strike','Reference IV','Comparison IV','Change (pp)','Reference data','Comparison data']);
header('I38:L38',['Date','Watched-strike IV','Vs reference (pp)','Selected days']);
header('W38:Y38',['Strike','Reference day','Comparison day']);header('AA38:AB38',['Date','Watched-strike IV']);
for(let i=0;i<26;i++){
 const r=39+i,g=72+i;f(`A${r}`,`=A${g}`);
 for(const [c,date] of [['B','B7'],['C','B9']]){
  const look=`INDEX($B${g}:$T${g},1,MATCH($${date},$B$71:$T$71,0))`;
  f(`${c}${r}`,`=IF($D$6<>"Ready","",IF(ISNUMBER(${look}),${look},""))`);
 }
 f(`D${r}`,`=IF(AND(ISNUMBER(B${r}),ISNUMBER(C${r})),100*(C${r}-B${r}),"")`);
 f(`E${r}`,`=IF(ISNUMBER(B${r}),"Available","No screened IV")`);f(`F${r}`,`=IF(ISNUMBER(C${r}),"Available","No screened IV")`);
 f(`W${r}`,`=A${r}`);f(`X${r}`,`=IF(ISNUMBER(B${r}),B${r},NA())`);f(`Y${r}`,`=IF(ISNUMBER(C${r}),C${r},NA())`);
}
for(let i=0;i<19;i++){
 const r=39+i,c=col(i+1);f(`I${r}`,`=${c}71`);
 const look=`INDEX($B$72:$T$97,MATCH($B$10,$A$72:$A$97,0),${i+1})`;
 f(`J${r}`,`=IF(OR($D$6<>"Ready",COUNTIFS($A$72:$A$97,$B$10)<>1),"",IF(ISNUMBER(${look}),${look},""))`);
 const ref=`INDEX($J$39:$J$57,MATCH($B$7,$I$39:$I$57,0))`;
 f(`K${r}`,`=IF($D$6<>"Ready","",IF(AND(ISNUMBER(J${r}),ISNUMBER(${ref})),100*(J${r}-${ref}),""))`);
 f(`L${r}`,`=IF($D$6<>"Ready","",IF(I${r}=$B$7,"Reference",IF(I${r}=$B$9,"Comparison","")))`);
 f(`AA${r}`,`=TEXT(I${r},"dd-mmm")`);f(`AB${r}`,`=IF(ISNUMBER(J${r}),J${r},NA())`);
}
s.getRange('A39:A64').setNumberFormat('#,##0');s.getRange('B39:C64').setNumberFormat('0.0%');s.getRange('D39:D64').setNumberFormat('+0.0" pp";-0.0" pp";0.0" pp"');s.getRange('I39:I57').setNumberFormat('dd-mmm-yy');s.getRange('J39:J57').setNumberFormat('0.0%');s.getRange('K39:K57').setNumberFormat('+0.0" pp";-0.0" pp";0.0" pp"');
s.getRange('D39:D64').conditionalFormats.add('cellIs',{operator:'greaterThan',formula:0,format:{font:{color:'#B26424'}}});s.getRange('D39:D64').conditionalFormats.add('cellIs',{operator:'lessThan',formula:0,format:{font:{color:blue}}});
f('H12','=IF(COUNTIFS(\'IV history\'!$C$7:$C$926,B6,\'IV history\'!$D$7:$D$926,B10)=0,"Watch strike unavailable for this type",IF(COUNT($J$39:$J$57)=0,"No screened IV for the watched strike","Watched-strike chart shows all available sessions."))');s.mergeCells('H12:N12');s.getRange('H12:N12').format.wrapText=true;
f('D12','=IF(D6="Ready","Comparison minus reference, in volatility percentage points.","Choose an available day and session step.")');s.mergeCells('D12:G12');s.getRange('D12:G12').format.wrapText=true;s.getRange('A12:N12').format.rowHeight=32;
v('W35','Chart helpers: #N/A deliberately leaves gaps.');
function chart(type,range,title,start,end){const c=s.charts.add(type,range);c.title=title;c.setPosition(start,end);c.titleTextStyle.fontSize=13;c.titleTextStyle.typeface='Arial';c.legend={position:'bottom',textStyle:{typeface:'Arial',fontSize:10}};c.xAxis={textStyle:{typeface:'Arial',fontSize:10}};c.yAxis={numberFormatCode:'0%',numberFormatSourceLinked:false,textStyle:{typeface:'Arial',fontSize:10}};c.series.items.forEach((x,i)=>x.line={fill:i?blue:orange,width:2,style:'solid'});return c;}
const curve=chart('scatter',s.getRange('W38:Y64'),'IV curve by strike: reference vs comparison','A17','G35');curve.xAxis.title.text='Strike (ARS)';curve.xAxis.numberFormatCode='#,##0';curve.xAxis.numberFormatSourceLinked=false;
const history=chart('line',s.getRange('AA38:AB57'),'Selected strike: daily IV','H17','N35');history.xAxis.axisType='textAxis';
// Check forward, backward, same-day, type changes, missing IV and out-of-range steps.
const lookup=new Map(data.rows.map(x=>[`${x.date}|${x.side}|${x.k}`,x.iv]));let checked=0;
const serial=day=>Date.parse(day+'T00:00:00Z')/86400000+25569;
function test(type,index,step){v('B6',type);v('B7',serial(data.daily[index].date));v('B8',step);if(s.getRange('D6').values[0][0]!=='Ready')throw Error('Valid selection rejected');
 for(let i=0;i<26;i++){const r=39+i,vals=s.getRange(`B${r}:D${r}`).values[0],expected=[lookup.get(`${data.daily[index].date}|${type}|${cs[i]}`),lookup.get(`${data.daily[index+step].date}|${type}|${cs[i]}`)];expected.forEach((x,j)=>{if(typeof x==='number'){if(typeof vals[j]!=='number'||Math.abs(vals[j]-x)>1e-9)throw Error('Curve mismatch');}else if(vals[j]!==''&&vals[j]!==null)throw Error('Missing IV became zero');checked++;});if(expected.every(x=>typeof x==='number')&&Math.abs(vals[2]-100*(expected[1]-expected[0]))>1e-8)throw Error('IV difference mismatch');}
}
test('call',7,1);test('call',18,-1);test('put',0,18);test('put',7,0);
for(const [idx,step] of [[0,-1],[18,1],[7,.5]]){v('B7',serial(data.daily[idx].date));v('B8',step);if(s.getRange('D6').values[0][0]==='Ready'||typeof s.getRange('B39').values[0][0]==='number')throw Error('Invalid step accepted');checked++;}
test('call',7,1);v('B10',7000);for(let i=0;i<19;i++){const val=s.getRange(`J${39+i}`).values[0][0],x=lookup.get(`${data.daily[i].date}|call|7000`);if(typeof x==='number'&&Math.abs(val-x)>1e-9)throw Error('Watched strike mismatch');checked++;}v('B10',6800);
wb.recalculate();console.log('Curve selection checks:',checked);
console.log((await wb.inspect({kind:'table',range:'IV curve explorer!A51:F53',include:'values,formulas',tableMaxRows:3,tableMaxCols:6})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!|#SPILL!',options:{useRegex:true,maxResults:10},summary:'Unexpected errors'})).ndjson);
await(await SpreadsheetFile.exportXlsx(wb)).save(fileURLToPath(target));
for(const [range,name] of [['A1:N35','iv_curve_controls.png'],['A38:L64','iv_curve_detail.png'],['A68:T97','iv_heatmap.png']]){const image=await wb.render({sheetName:'IV curve explorer',range,scale:1,format:'png'});await fs.writeFile(new URL(name,dir),new Uint8Array(await image.arrayBuffer()));}
console.log('IV curve explorer saved.');
