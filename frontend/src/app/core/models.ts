/** Tipos compartidos que reflejan el contrato de la API. */

export type FileType = 'pdf' | 'word' | 'presentation' | 'repository' | 'any';
export type SourceName = 'openalex' | 'arxiv';

export interface SearchQuery {
  query: string;
  year_from?: number | null;
  year_to?: number | null;
  language?: string | null;
  file_types: FileType[];
  sources: SourceName[];
  limit: number;
}

export interface ResourceItem {
  title: string;
  authors: string[];
  year: number | null;
  language: string | null;
  description: string | null;
  landing_url: string | null;
  download_url: string | null;
  file_type: FileType;
  source: SourceName;
  repository: string | null;
  open_access: boolean;
  relevance: number;
}

export interface SearchResponse {
  query: SearchQuery;
  total: number;
  results: ResourceItem[];
  took_ms: number;
  generated_at: string;
  warnings: string[];
}
