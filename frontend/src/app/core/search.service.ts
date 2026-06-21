import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import {
  DownloadResponse,
  HarvestRequest,
  HarvestResponse,
  SearchQuery,
  SearchResponse,
} from './models';

/** Cliente del backend de búsqueda, cosecha y descarga. */
@Injectable({ providedIn: 'root' })
export class SearchService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  search(query: SearchQuery): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.baseUrl}/search`, query);
  }

  harvest(request: HarvestRequest): Observable<HarvestResponse> {
    return this.http.post<HarvestResponse>(`${this.baseUrl}/harvest`, request);
  }

  download(urls: string[]): Observable<DownloadResponse> {
    return this.http.post<DownloadResponse>(`${this.baseUrl}/download`, { urls });
  }
}
