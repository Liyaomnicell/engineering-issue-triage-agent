import { Component, OnInit, OnDestroy, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Api, Case, Evidence, IndexStatus } from './api';
const blank=():Case=>({title:'',question:'',description:'',sourceUrl:'',version:'',history:[]});
@Component({selector:'app-root',imports:[CommonModule,FormsModule],templateUrl:'./app.html',styleUrl:'./app.css'})
export class App implements OnInit,OnDestroy {
  private api=inject(Api);
  private timer?:ReturnType<typeof setInterval>;
  case:Case=blank(); kind='all'; repo='';
  cases=signal<Case[]>([]); results=signal<Evidence[]>([]); selected=signal<Evidence|null>(null);
  status=signal<IndexStatus>({running:false,ready:false,phase:'Connecting to PostgreSQL',files:0,chunks:0,skipped:0,errors:[]});
  busy=signal(false); searched=signal(false); message=signal(''); error=signal(false); packet='';
  suggestions=[{title:'Investigate a workflow',detail:'AMR waste and transfer transactions',query:'AMR reconciliation anesthesia waste transfer missing items'},{title:'Trace a hardware event',detail:'MedChill lid and latch behavior',query:'DeviceSecure MedChill latch lid closed'},{title:'Find a related investigation',detail:'Syringe labels and barcode printing',query:'syringe label printing barcode dispensing alerts'}];
  async ngOnInit(){await Promise.all([this.refresh(),this.refreshCases()]);this.timer=setInterval(()=>this.refresh(),5000);}
  ngOnDestroy(){if(this.timer)clearInterval(this.timer);}
  notify(text:string,isError=false){this.message.set(text);this.error.set(isError);}
  fail(error:unknown){const e=error as {error?:{error?:string};message?:string};this.notify(e.error?.error || e.message || 'The local API could not complete the request. Check PostgreSQL and server availability.',true);}
  async refresh(){try{const response=await this.api.get<{index:IndexStatus}>('status');this.status.set(response.index);}catch(e){this.fail(e);}}
  async refreshCases(){try{this.cases.set(await this.api.get<Case[]>('investigations'));}catch(e){this.fail(e);}}
  async save(silent=false):Promise<void>{this.case.title=this.case.title.trim()||this.case.question.trim().slice(0,100)||'Untitled investigation';const logs=this.case.logs;this.case={...await this.api.post<Case>('investigation',this.case),logs};await this.refreshCases();if(!silent)this.notify('Investigation saved in PostgreSQL.');}
  async saveClicked(){try{await this.save();}catch(e){this.fail(e);}}
  async load(id?:string){if(!id||this.busy())return;try{this.case=await this.api.get<Case>('investigation?id='+encodeURIComponent(id));this.results.set([]);this.selected.set(null);this.searched.set(false);this.packet='';this.notify('Investigation loaded from PostgreSQL. Search again for current evidence.');}catch(e){this.fail(e);}}
  newCase(){if(this.busy())return;if((this.case.question||this.case.description||this.case.title)&&!confirm('Start a new investigation? Save any unsaved changes first.'))return;this.case=blank();this.results.set([]);this.selected.set(null);this.searched.set(false);this.message.set('');this.packet='';}
  choose(query:string){this.case.question=query;}
  async search(){if(this.busy())return;if(!this.case.question.trim())return this.notify('Enter a question or code symbol.',true);if(!this.status().ready&&this.kind!=='log')return this.notify('Build or migrate the PostgreSQL knowledge index first.',true);this.busy.set(true);try{await this.save(true);const response=await this.api.post<import('./api').SearchResponse>('search',{question:this.case.question,kind:this.kind,repo:this.repo,caseId:this.case.id});this.results.set(response.results);this.selected.set(response.results[0]||null);this.packet=response.packet;this.searched.set(true);this.case.history=[...this.case.history,{question:this.case.question,time:new Date().toISOString(),count:response.results.length}].slice(-100);await this.save(true);this.message.set('');}catch(e){this.fail(e);}finally{this.busy.set(false);}}
  async rebuild(){try{await this.api.post('index',{});await this.refresh();this.notify('PostgreSQL index rebuild started. The previous generation stays available until completion.');}catch(e){this.fail(e);}}
  sourceLink(source:Evidence):string|null{return source.url&&/^https:\/\/(bitbucket\.org|omnicell-eng\.atlassian\.net)\//.test(source.url)?source.url:null;}
  async upload(event:Event){const input=event.target as HTMLInputElement;const files=Array.from(input.files||[]);this.busy.set(true);try{await this.save(true);for(const file of files){if(file.size>20*1024*1024)throw new Error('Upload exceeds 20 MB');this.notify('Adding '+file.name+'…');const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});await this.api.post('log',{id:this.case.id,name:file.name,data});}this.case=await this.api.get<Case>('investigation?id='+this.case.id);this.notify('Logs saved locally and scoped to this investigation.');}catch(e){this.fail(e);}finally{input.value='';this.busy.set(false);}}
  export(){const url=URL.createObjectURL(new Blob([this.packet],{type:'text/markdown;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`investigation-${this.case.id||'new'}-evidence.md`;link.click();setTimeout(()=>URL.revokeObjectURL(url),5000);}
}
