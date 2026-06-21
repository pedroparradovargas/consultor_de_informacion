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
import { FileType, ResourceItem, SearchResponse, SourceName } from './core/models';
import { SearchService } from './core/search.service';
import { ResultCardComponent } from './features/result-card.component';

interface ToggleOption<T> {
  value: T;
  label: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, ResultCardComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  private readonly fb = inject(FormBuilder);
  private readonly searchService = inject(SearchService);

  /** Año actual para validar el rango del lapso. */
  readonly currentYear = new Date().getFullYear();

  readonly fileTypeOptions: ToggleOption<FileType>[] = [
    { value: 'any', label: 'Todos' },
    { value: 'pdf', label: 'PDF' },
    { value: 'word', label: 'Word' },
    { value: 'presentation', label: 'Presentaciones' },
    { value: 'repository', label: 'Repositorios' },
  ];

  readonly sourceOptions: ToggleOption<SourceName>[] = [
    { value: 'openalex', label: 'OpenAlex' },
    { value: 'arxiv', label: 'arXiv' },
  ];

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

  readonly form: FormGroup = this.fb.group({
    query: this.fb.control('', {
      validators: [Validators.required, Validators.minLength(2)],
      nonNullable: true,
    }),
    yearFrom: new FormControl<number | null>(null),
    yearTo: new FormControl<number | null>(null),
    language: this.fb.control('', { nonNullable: true }),
    fileTypes: this.fb.control<FileType[]>(['any'], { nonNullable: true }),
    sources: this.fb.control<SourceName[]>(['openalex', 'arxiv'], { nonNullable: true }),
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

    this.searchService
      .search({
        query: raw.query.trim(),
        year_from: raw.yearFrom || null,
        year_to: raw.yearTo || null,
        language: raw.language || null,
        file_types: raw.fileTypes,
        sources: raw.sources,
        limit: raw.limit,
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
}
