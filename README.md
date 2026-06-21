# 🛰️ Consultor de Información

> Motor de búsqueda **OSINT académico**: encuentra manuales, cartillas y recursos
> educativos en **fuentes abiertas** (universidades, repositorios y catálogos
> científicos), con filtros por **lapso (año), temario, idioma, tipo de archivo y
> repositorio**. Interfaz **cyberpunk hiperrealista**.

---

## ✨ Características

- 🔎 **Búsqueda agregada y concurrente** sobre múltiples fuentes abiertas.
- 🗓️ **Filtros**: lapso de años, temario/palabras clave, idioma, tipo de archivo
  (PDF, Word, presentaciones, repositorios) y fuente.
- 🌐 **Fuentes 100 % legales y abiertas** (sin scraping agresivo):
  [OpenAlex](https://openalex.org) y [arXiv](https://arxiv.org). Arquitectura
  ampliable a más fuentes con un solo archivo.
- 🧱 **Resultados normalizados**: título, autores, año, idioma, resumen,
  repositorio, enlace de descarga y de fuente.
- 🛡️ **Seguro por diseño**: validación estricta de entrada, límite de tasa,
  CORS restringido, timeouts y User-Agent honesto.
- 🎨 **UI cyberpunk**: glassmorphism, neón, rejilla en perspectiva, glitch y
  scanlines; totalmente responsive.

## 🏗️ Arquitectura

```
consultor_de_informacion/
├── backend/                 # API REST · Python 3.11 + FastAPI
│   └── app/
│       ├── main.py          # App, CORS, logging
│       ├── config.py        # Configuración (Pydantic Settings / .env)
│       ├── api/routes.py     # Endpoints REST
│       ├── core/security.py  # Rate limiting + cliente HTTP seguro
│       ├── models/schemas.py # Contratos de datos (Pydantic)
│       └── services/
│           ├── aggregator.py # Orquestación concurrente + dedup + ranking
│           └── sources/      # Conectores (openalex, arxiv, base)
└── frontend/                # SPA · Angular 19 (standalone + signals)
    └── src/app/
        ├── app.component.*   # Vista principal (formulario + resultados)
        ├── core/             # Modelos + servicio HTTP
        └── features/         # Tarjeta de resultado
```

**Stack:** Angular 19 (frontend más robusto y seguro, con signals y componentes
standalone) + FastAPI (mejor ecosistema Python para OSINT/scraping).

## 🚀 Puesta en marcha

### 1. Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # opcional: configura CONTACT_EMAIL
uvicorn app.main:app --reload      # http://localhost:8000  (docs en /docs)
```

### 2. Frontend (Angular)

```bash
cd frontend
npm install
npm start                          # http://localhost:4200
```

El frontend en modo desarrollo apunta a `http://localhost:8000/api`.

## 🔌 API

| Método | Ruta           | Descripción                         |
| ------ | -------------- | ----------------------------------- |
| `GET`  | `/api/health`  | Estado del servicio                 |
| `GET`  | `/api/sources` | Fuentes disponibles                 |
| `POST` | `/api/search`  | Búsqueda agregada de recursos       |

Ejemplo de cuerpo para `POST /api/search`:

```json
{
  "query": "cálculo diferencial",
  "year_from": 2018,
  "year_to": 2024,
  "language": "es",
  "file_types": ["pdf"],
  "sources": ["openalex", "arxiv"],
  "limit": 25
}
```

## 🔒 Seguridad y uso responsable

- Solo se consultan **APIs abiertas y públicas** que permiten acceso programático.
- Se respeta el "polite pool" de OpenAlex (User-Agent + correo de contacto).
- Límite de tasa por IP, CORS restringido, timeouts y validación estricta.
- Esta herramienta es para **fines educativos y de investigación**. Respeta los
  derechos de autor y las licencias de cada recurso descargado.

> ⚠️ **Nota sobre el entorno remoto:** en este entorno de ejecución la política
> de red puede bloquear las llamadas salientes (403). La app degrada con
> elegancia (devuelve 0 resultados y un aviso). En una red con salida abierta,
> las búsquedas funcionan con normalidad.

## 🧭 Mejoras propuestas (roadmap)

Lo que recomiendo añadir para llevarlo a producción:

1. **Más fuentes**: DOAJ, CORE, BASE, Semantic Scholar, Zenodo, Internet Archive
   y buscadores de repositorios universitarios (DSpace / OAI-PMH).
2. **Scraper de sitios `.edu`** con respeto a `robots.txt` y Playwright para
   páginas dinámicas, como complemento opcional.
3. **Caché** (Redis) de búsquedas y **cola de descargas** asíncrona.
4. **Autenticación** (JWT/OAuth) e historial de búsquedas por usuario.
5. **Exportación** de resultados a CSV/BibTeX y guardado en colecciones.
6. **Vista previa** del PDF y extracción de texto/temario con IA.
7. **Internacionalización** (i18n) de la interfaz.
8. **Tests** (pytest + Vitest/Karma) y **CI/CD** con GitHub Actions.
9. **Contenedores** Docker + `docker-compose` para un despliegue de un comando.
