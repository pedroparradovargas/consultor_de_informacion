import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, NgZone, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  DownloadJobCreated,
  DownloadProgressEvent,
  HarvestRequest,
  HarvestResponse,
  RepositoryInfo,
  SearchQuery,
  SearchResponse,
} from './models';

/** Cliente del backend de búsqueda, cosecha y descarga. */
@Injectable({ providedIn: 'root' })
export class SearchService {
  private readonly http = inject(HttpClient);
  private readonly zone = inject(NgZone);
  private readonly baseUrl = environment.apiBaseUrl;

  search(query: SearchQuery): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.baseUrl}/search`, query);
  }

  harvest(request: HarvestRequest): Observable<HarvestResponse> {
    return this.http.post<HarvestResponse>(`${this.baseUrl}/harvest`, request);
  }

  discoverRepositories(q?: string, country?: string): Observable<RepositoryInfo[]> {
    let params = new HttpParams();
    if (q) params = params.set('q', q);
    if (country) params = params.set('country', country);
    return this.http.get<RepositoryInfo[]>(`${this.baseUrl}/repositories`, { params });
  }

  createDownloadJob(urls: string[]): Observable<DownloadJobCreated> {
    return this.http.post<DownloadJobCreated>(`${this.baseUrl}/download/jobs`, { urls });
  }

  /** Suscribe al progreso de un trabajo de descarga mediante SSE. */
  streamDownload(jobId: string): Observable<DownloadProgressEvent> {
    return new Observable<DownloadProgressEvent>((subscriber) => {
      const source = new EventSource(
        `${this.baseUrl}/download/jobs/${jobId}/events`,
      );
      source.onmessage = (msg) => {
        const data = JSON.parse(msg.data) as DownloadProgressEvent;
        // EventSource emite fuera de la zona de Angular → reentrar para refrescar.
        this.zone.run(() => {
          subscriber.next(data);
          if (data.event === 'done') {
            subscriber.complete();
            source.close();
          }
        });
      };
      source.onerror = () => {
        this.zone.run(() => subscriber.complete());
        source.close();
      };
      return () => source.close();
    });
  }
}
