import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import {
  FormBuilder,
  FormControl,
  FormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { finalize } from 'rxjs';
import {
  DownloadProgressEvent,
  FileType,
  ResourceItem,
  SearchResponse,
  SourceName,
} from './core/models';
import { SearchService } from './core/search.service';
import { RepositoryPanelComponent } from './features/repository-panel.component';
import { ResultCardComponent } from './features/result-card.component';

type AppMode = 'search' | 'repository';

interface ToggleOption<T> {
  value: T;
  label: string;
}

/** Estado de una descarga masiva en curso. */
interface BulkDownload {
  completed: number;
  downloaded: number;
  total: number;
  done: boolean;
  dir?: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ResultCardComponent,
    RepositoryPanelComponent,
  ],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly fb = inject(FormBuilder);
  private readonly searchService = inject(SearchService);

  /** Año actual para validar el rango del lapso. */
  readonly currentYear = new Date().getFullYear();

  /** Modo activo de la interfaz. */
  readonly mode = signal<AppMode>('search');

  setMode(mode: AppMode): void {
    this.mode.set(mode);
  }

  readonly fileTypeOptions: ToggleOption<FileType>[] = [
    { value: 'any', label: 'Todos' },
    { value: 'pdf', label: 'PDF' },
    { value: 'word', label: 'Word' },
    { value: 'presentation', label: 'Presentaciones' },
    { value: 'repository', label: 'Repositorios' },
  ];

  readonly sourceOptions: ToggleOption<SourceName>[] = [
    { value: 'internet_archive', label: '📚 Libros (Internet Archive)' },
    { value: 'openalex', label: 'OpenAlex' },
    { value: 'arxiv', label: 'arXiv' },
  ];

  readonly limitOptions = [25, 50, 100, 200];

  readonly languageOptions = [
    { value: '', label: 'Cualquiera' },
    { value: 'es', label: 'Español' },
    { value: 'en', label: 'Inglés' },
    { value: 'pt', label: 'Portugués' },
    { value: 'fr', label: 'Francés' },
  ];

  // --- Estado reactivo con signals ---
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly response = signal<SearchResponse | null>(null);
  readonly results = computed<ResourceItem[]>(() => this.response()?.results ?? []);

  /** Recursos con enlace de descarga directa (PDF). */
  readonly downloadable = computed<ResourceItem[]>(() =>
    this.results().filter((r) => !!r.download_url),
  );

  /** Estado de la descarga masiva ("descargar todos"). */
  readonly bulk = signal<BulkDownload | null>(null);
  readonly bulkRunning = signal(false);

  readonly form: FormGroup = this.fb.group({
    query: this.fb.control('', {
      validators: [Validators.required, Validators.minLength(2)],
      nonNullable: true,
    }),
    yearFrom: new FormControl<number | null>(null),
    yearTo: new FormControl<number | null>(null),
    language: this.fb.control('', { nonNullable: true }),
    fileTypes: this.fb.control<FileType[]>(['any'], { nonNullable: true }),
    sources: this.fb.control<SourceName[]>(
      ['internet_archive', 'openalex', 'arxiv'],
      { nonNullable: true },
    ),
    limit: this.fb.control(25, { nonNullable: true }),
  });

  isFileTypeSelected(value: FileType): boolean {
    return (this.form.controls['fileTypes'].value as FileType[]).includes(value);
  }

  isSourceSelected(value: SourceName): boolean {
    return (this.form.controls['sources'].value as SourceName[]).includes(value);
  }

  toggleFileType(value: FileType): void {
    const control = this.form.controls['fileTypes'];
    let current = [...(control.value as FileType[])];
    if (value === 'any') {
      current = ['any'];
    } else {
      current = current.filter((v) => v !== 'any');
      current = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      if (current.length === 0) current = ['any'];
    }
    control.setValue(current);
  }

  toggleSource(value: SourceName): void {
    const control = this.form.controls['sources'];
    const current = [...(control.value as SourceName[])];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    control.setValue(next);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const raw = this.form.getRawValue();
    if (raw.yearFrom && raw.yearTo && raw.yearFrom > raw.yearTo) {
      this.error.set('El año inicial no puede ser mayor que el final.');
      return;
    }
    if ((raw.sources as SourceName[]).length === 0) {
      this.error.set('Selecciona al menos una fuente.');
      return;
    }

    this.error.set(null);
    this.loading.set(true);
    this.response.set(null);
    this.bulk.set(null);
    this.bulkRunning.set(false);

    this.searchService
      .search({
        query: raw.query.trim(),
        year_from: raw.yearFrom || null,
        year_to: raw.yearTo || null,
        language: raw.language || null,
        file_types: raw.fileTypes,
        sources: raw.sources,
        limit: Number(raw.limit) || 25,
        verify_links: true,
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (res) => this.response.set(res),
        error: () =>
          this.error.set(
            'No se pudo completar la búsqueda. Verifica que el backend esté activo.',
          ),
      });
  }

  /** Descarga directamente todos los PDFs de los resultados (job + progreso SSE). */
  downloadAll(): void {
    const urls = this.downloadable()
      .map((r) => r.download_url!)
      .filter((u, i, arr) => arr.indexOf(u) === i);
    if (urls.length === 0) {
      this.error.set('No hay libros con enlace de descarga directa.');
      return;
    }

    this.error.set(null);
    this.bulkRunning.set(true);
    this.bulk.set({ completed: 0, downloaded: 0, total: urls.length, done: false });

    this.searchService.createDownloadJob(urls).subscribe({
      next: (job) => this.listenBulkProgress(job.job_id, job.total),
      error: () => {
        this.bulkRunning.set(false);
        this.error.set('No se pudo iniciar la descarga masiva.');
      },
    });
  }

  private listenBulkProgress(jobId: string, total: number): void {
    let downloaded = 0;
    this.searchService.streamDownload(jobId).subscribe({
      next: (e: DownloadProgressEvent) => {
        if (e.event === 'progress') {
          if (e.status === 'downloaded') downloaded += 1;
          this.bulk.set({
            completed: e.completed ?? 0,
            downloaded,
            total,
            done: false,
          });
        } else if (e.event === 'done') {
          this.bulk.set({
            completed: total,
            downloaded: e.downloaded ?? 0,
            total,
            done: true,
            dir: e.download_dir,
          });
          this.bulkRunning.set(false);
        }
      },
      error: () => {
        this.bulkRunning.set(false);
        this.error.set('Se perdió la conexión con el progreso de descarga.');
      },
      complete: () => this.bulkRunning.set(false),
    });
  }
}
