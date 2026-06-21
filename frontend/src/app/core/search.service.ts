import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { SearchQuery, SearchResponse } from './models';

/** Cliente del backend de búsqueda. */
@Injectable({ providedIn: 'root' })
export class SearchService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  search(query: SearchQuery): Observable<SearchResponse> {
    return this.http.post<SearchResponse>(`${this.baseUrl}/search`, query);
  }
}
