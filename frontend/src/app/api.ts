import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
export interface Evidence { id?:number; kind:string; title:string; path:string; text:string; citation:string; repo?:string; branch?:string; commit_sha?:string; url?:string; rank?:number; }
export interface History { question:string; time:string; count:number; }
export interface Case { id?:string; title:string; question:string; description:string; sourceUrl:string; version:string; history:History[]; updated?:string; logs?:{file:string;bytes:number}[]; }
export interface IndexStatus { running:boolean; ready:boolean; phase:string; chunks:number; files:number; skipped:number; completed?:string; errors:{path:string;error:string}[]; repositories?:{name:string;branch:string;commit:string}[]; database?:string; }
export interface SearchResponse { results:Evidence[]; packet:string; generated:boolean; index:IndexStatus; }
@Injectable({providedIn:'root'})
export class Api {
  private http=inject(HttpClient);
  get<T>(path:string):Promise<T> { return firstValueFrom(this.http.get<T>('/api/'+path)); }
  post<T>(path:string,body:unknown):Promise<T> { return firstValueFrom(this.http.post<T>('/api/'+path,body,{headers:{'X-Triage-Request':'1'}})); }
}
