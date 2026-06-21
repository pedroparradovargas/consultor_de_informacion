import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import {
  DownloadResponse,
  HarvestResponse,
  ResourceItem,
} from '../core/models';
import { SearchService } from '../core/search.service';

/** Panel de cosecha OAI-PMH y descarga responsable de PDFs abiertos. */
@Component({
  selector: 'app-repository-panel',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './repository-panel.component.html',
  styleUrl: './repository-panel.component.scss',
})
export class RepositoryPanelComponent {
  private readonly fb = inject(FormBuilder);
  private readonly service = inject(SearchService);

  readonly currentYear = new Date().getFullYear();

  readonly harvesting = signal(false);
  readonly downloading = signal(false);
  readonly error = signal<string | null>(null);
  readonly harvest = signal<HarvestResponse | null>(null);
  readonly downloadResult = signal<DownloadResponse | null>(null);

  /** URLs de descarga seleccionadas por el usuario. */
  readonly selected = signal<Set<string>>(new Set());

  readonly downloadable = computed<ResourceItem[]>(() =>
    (this.harvest()?.results ?? []).filter((r) => !!r.download_url),
  );

  readonly form: FormGroup = this.fb.group({
    baseUrl: this.fb.control('', {
      validators: [Validators.required, Validators.pattern(/^https?:\/\/.+/)],
      nonNullable: true,
    }),
    setSpec: this.fb.control('', { nonNullable: true }),
    yearFrom: this.fb.control<number | null>(null),
    yearTo: this.fb.control<number | null>(null),
    language: this.fb.control('', { nonNullable: true }),
    onlyOpenAccess: this.fb.control(true, { nonNullable: true }),
    maxRecords: this.fb.control(50, { nonNullable: true }),
  });

  isSelected(url: string): boolean {
    return this.selected().has(url);
  }

  toggle(url: string): void {
    const next = new Set(this.selected());
    next.has(url) ? next.delete(url) : next.add(url);
    this.selected.set(next);
  }

  selectAll(): void {
    this.selected.set(new Set(this.downloadable().map((r) => r.download_url!)));
  }

  clearSelection(): void {
    this.selected.set(new Set());
  }

  runHarvest(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Indica una URL OAI-PMH válida (http/https).');
      return;
    }
    const raw = this.form.getRawValue();
    this.error.set(null);
    this.harvesting.set(true);
    this.harvest.set(null);
    this.downloadResult.set(null);
    this.clearSelection();

    this.service
      .harvest({
        base_url: raw.baseUrl.trim(),
        set_spec: raw.setSpec || null,
        year_from: raw.yearFrom || null,
        year_to: raw.yearTo || null,
        language: raw.language || null,
        only_open_access: raw.onlyOpenAccess,
        max_records: raw.maxRecords,
      })
      .pipe(finalize(() => this.harvesting.set(false)))
      .subscribe({
        next: (res) => this.harvest.set(res),
        error: () =>
          this.error.set('No se pudo cosechar. Verifica la URL y el backend.'),
      });
  }

  runDownload(): void {
    const urls = [...this.selected()];
    if (urls.length === 0) {
      this.error.set('Selecciona al menos un PDF para descargar.');
      return;
    }
    this.error.set(null);
    this.downloading.set(true);
    this.downloadResult.set(null);

    this.service
      .download(urls)
      .pipe(finalize(() => this.downloading.set(false)))
      .subscribe({
        next: (res) => this.downloadResult.set(res),
        error: () => this.error.set('La descarga falló. Revisa el backend.'),
      });
  }
}
