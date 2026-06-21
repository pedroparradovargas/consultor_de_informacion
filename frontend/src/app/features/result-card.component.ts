import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { ResourceItem } from '../core/models';

/** Tarjeta que muestra un recurso educativo encontrado. */
@Component({
  selector: 'app-result-card',
  standalone: true,
  imports: [CommonModule],
  template: `
    <article class="card">
      <div class="card__head">
        <span class="card__badge card__badge--{{ item.file_type }}">
          {{ fileTypeLabel(item.file_type) }}
        </span>
        @if (item.open_access) {
          <span class="card__oa">Acceso abierto</span>
        }
        @if (item.year) {
          <span class="card__year">{{ item.year }}</span>
        }
      </div>

      <h3 class="card__title">{{ item.title }}</h3>

      @if (item.authors.length) {
        <p class="card__authors">{{ item.authors.slice(0, 4).join(' · ') }}</p>
      }

      @if (item.description) {
        <p class="card__desc">{{ item.description }}</p>
      }

      <div class="card__foot">
        <span class="card__repo">
          @if (item.repository) {
            ⌂ {{ item.repository }}
          } @else {
            ⌂ Fuente: {{ item.source }}
          }
        </span>
        <div class="card__actions">
          @if (item.download_url) {
            <a class="btn btn--primary" [href]="item.download_url" target="_blank" rel="noopener noreferrer">
              Descargar
            </a>
          }
          @if (item.landing_url) {
            <a class="btn" [href]="item.landing_url" target="_blank" rel="noopener noreferrer">
              Ver fuente
            </a>
          }
        </div>
      </div>
    </article>
  `,
  styleUrl: './result-card.component.scss',
})
export class ResultCardComponent {
  @Input({ required: true }) item!: ResourceItem;

  fileTypeLabel(type: string): string {
    const map: Record<string, string> = {
      pdf: 'PDF',
      word: 'WORD',
      presentation: 'SLIDES',
      repository: 'REPO',
      any: 'DOC',
    };
    return map[type] ?? 'DOC';
  }
}
