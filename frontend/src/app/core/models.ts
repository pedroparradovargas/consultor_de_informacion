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

// ---- Cosecha OAI-PMH y descarga de repositorios ----

export interface HarvestRequest {
  base_url: string;
  set_spec?: string | null;
  year_from?: number | null;
  year_to?: number | null;
  language?: string | null;
  only_open_access: boolean;
  max_records: number;
}

export interface HarvestResponse {
  base_url: string;
  total: number;
  results: ResourceItem[];
  took_ms: number;
  warnings: string[];
}

export type DownloadStatus = 'downloaded' | 'skipped' | 'blocked' | 'failed';

export interface DownloadResultItem {
  url: string;
  status: DownloadStatus;
  reason: string | null;
  path: string | null;
  size_bytes: number | null;
}

export interface DownloadResponse {
  total: number;
  downloaded: number;
  results: DownloadResultItem[];
  download_dir: string;
}
