# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Sistema web de facturación electrónica AFIP (Argentina): FastAPI + SQLAlchemy + Jinja2,
integrando los web services WSAA (autenticación), WSFEv1 (CAE) y el Padrón A5
(constancia de inscripción) vía `pyafipws`. La documentación de usuario está en
`README.md`; este archivo cubre lo que no es obvio leyendo un solo archivo.

## Entorno e instalación (puntos críticos, no obvios)

- **Usar siempre el intérprete del venv:** `.venv\Scripts\python.exe`. uvicorn
  necesita `--app-dir` apuntando a la raíz (o CWD = raíz) para encontrar `app`.
- **`pyafipws` NO se instala desde `requirements.txt`:** la versión de PyPI
  (`PyAfipWs`) es **Python 2** y no corre en Python 3. La versión Python 3 está en
  GitHub y se instala aparte y sin dependencias (las que fija rompen en 3.13):
  ```
  pip install --no-deps git+https://github.com/reingart/pyafipws.git
  ```
  Sus dependencias de runtime (`future`, `pysimplesoap==1.8.22`, `httplib2`,
  `certifi`, `setuptools<74`) ya están en `requirements.txt`.
- **Shims para pyafipws en Python 3.12+** (patrón a repetir si se integra otro
  módulo de pyafipws):
  - `distutils` (lo importa `pysimplesoap`): se fija `setuptools<74`, que
    restituye el shim al arrancar el intérprete.
  - `configparser.SafeConfigParser` (lo importa `ws_sr_padron`): se restituye
    **antes del import** en `app/afip/padron_client.py`
    (`configparser.SafeConfigParser = configparser.ConfigParser`).
- **`bcrypt` directo, no `passlib`** (passlib quedó sin mantenimiento e
  incompatible con bcrypt 5.x). Ver `app/auth/security.py`.

## Comandos

```powershell
# Instalar (tras crear venv)
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps git+https://github.com/reingart/pyafipws.git

# Base de datos: crear 'facturas_afip' en MySQL, luego tablas + usuario admin
.\.venv\Scripts\python.exe scripts/init_db.py

# Registrar empresa emisora desde un .p12 (extrae .crt/.key y lee el CUIT del cert)
.\.venv\Scripts\python.exe scripts/preparar_certificado.py --p12 "ruta\cert.p12" [--password CLAVE]

# Levantar la app web
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --app-dir "<raiz-del-proyecto>"

# Emitir una Factura B de ejemplo (valida toda la cadena contra homologación)
.\.venv\Scripts\python.exe scripts/emitir_factura_ejemplo.py

# Prueba de humo contra homologación (autenticar + último autorizado)
.\.venv\Scripts\python.exe -m pytest -s tests/test_afip_homologacion.py

# Lint / formato
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m black .
```

> `ruff`, `black` y `pytest` figuran en `requirements.txt` pero pueden faltar en
> el venv actual; si los comandos fallan con "No module named …", instalarlos:
> `pip install ruff black pytest`.

## Migraciones de esquema (no hay Alembic)

`Base.metadata.create_all` (desde `scripts/init_db.py`) **crea tablas nuevas pero
NO agrega columnas a tablas existentes**. Para cambios de esquema sobre una base
ya creada hay que ejecutar un `ALTER TABLE` one-off (script temporal con
`app.database.engine` + `sqlalchemy.text`, idempotente verificando
`SHOW COLUMNS`). Así se agregó `clientes.fecha_baja`.

## Arquitectura

Capas (de afuera hacia adentro): **routers** (web) → **services** (negocio) →
**afip** (protocolo AFIP) → `pyafipws`. Más **models** (ORM) y **auth**.

### Configuración dirigida por entorno (`app/config.py`)
`Settings` (pydantic-settings) lee `.env`. **`AFIP_MODO`** (`homologacion` |
`produccion`) resuelve automáticamente las URLs de WSAA/WSFEv1/Padrón A5 — el
resto del código nunca hardcodea URLs ni alterna entornos manualmente. `settings`
también expone `database_url`, `certs_path`, `pdfs_path`, etc.

### Capa AFIP aislada (`app/afip/`) — el núcleo
- `wsaa_client.autenticar(cuit, cert, key, servicio="wsfe")` devuelve un
  `TicketAcceso(token, sign, cuit)`. El Ticket de Acceso lo **cachea pyafipws en
  `.afip_cache/`** (válido ~12 h), un TA **por servicio**; no se re-autentica por
  operación.
- `wsfe_client`: `proximo_numero()` (CompUltimoAutorizado+1) y
  `emitir_comprobante(ticket, SolicitudCAE) -> ResultadoCAE`. Las dataclasses
  `SolicitudCAE`, `AlicuotaIva`, `CmpAsociado`, `ResultadoCAE` son la frontera
  tipada con pyafipws. Las fechas se pasan como `YYYY-MM-DD` y se convierten a
  `YYYYMMDD` internamente.
- `padron_client`: `consultar_constancia(ticket, cuit) -> DatosPadron` envuelve
  `WSSrPadronA5` (servicio **`ws_sr_constancia_inscripcion`** — el TA se pide con
  ese nombre de servicio, NO `wsfe`, y requiere **delegación propia** en el
  Administrador de Relaciones de AFIP). El `cat_iva` que devuelve AFIP usa los
  **mismos ids** que `COND_IVA_RECEPTOR_*`. En homologación el padrón tiene solo
  CUIT de prueba: los reales devuelven el SoapFault "No existe persona con ese
  Id" (se traduce a `AfipValidationError` "no encontrado", no a error de conexión).
- `constants.py`: códigos AFIP legibles y los mappers
  `iva_id_desde_porcentaje()`, `condicion_iva_receptor_id()` (texto→id) y
  `condicion_iva_receptor_texto()` (id→texto, para el padrón).
- `exceptions.py`: jerarquía `AfipError` → `AfipAuthError` /
  `AfipConnectionError` / `AfipValidationError` (esta última lleva
  `errores`/`observaciones` de AFIP).

### Flujo de emisión (`app/services/facturacion.py::emitir_factura`)
Orquesta todo: calcula neto/IVA/total **agrupando por alícuota** → autentica (TA
cacheado) → obtiene número → solicita CAE → **persiste el Comprobante + ítems solo
si AFIP aprobó** → genera el PDF (fallo de PDF no invalida el CAE). Reglas clave:
- **Factura C** (Monotributo, `LETRA_COMPROBANTE=="C"`): no discrimina IVA
  (`ivas=[]`, `imp_neto == total`).
- **Notas de crédito/débito**: requieren `cbte_asociado_id`; se traduce a
  `AgregarCmpAsociado`.
- **RG 5616 (obligatorio):** `condicion_iva_receptor_id` se deriva del texto
  `Cliente.condicion_iva` y se envía en `CrearFactura`. Si falta, AFIP rechaza con
  la observación **10246**.
- La **numeración la asigna AFIP**, no la base; se persiste recién tras el CAE.
- El **precio unitario** de cada línea viene del formulario (editable); si llega
  vacío/0 cae al `precio_unitario` del producto. Clientes con `fecha_baja` no
  pueden facturarse (guarda en el servicio + filtro en el form).

### Datos (`app/models/`)
Multiempresa: `Empresa` guarda `cert_path`/`key_path` **relativos a `certs/`** (la
base solo guarda la ruta; los PEM viven en disco). `Comprobante` guarda CAE,
vencimiento, resultado, `cbte_asociado_id` (autoreferencia para NC/ND) y `fecha`
como **string `"YYYY-MM-DD"`** (las agregaciones del dashboard agrupan por mes con
`substr(fecha,1,7)` y filtran rangos lexicográficamente). Bajas **lógicas**:
`Cliente.fecha_baja` (datetime NULL = activo) y flags `activo` en
`Empresa`/`Producto` — los combos de emisión filtran por ellos, nunca se borra
físicamente.

### Estadísticas (`app/services/estadisticas.py` + `/dashboard`)
Una sola query agrupa por mes+cliente; **las notas de crédito restan**
(`case` sobre `tipo_cbte in NOTAS_CREDITO`), solo comprobantes con CAE. El filtro
de período es **calendario en curso** (mensual/trimestral/semestral/anual) con
límite superior exclusivo. Los gráficos son Chart.js por CDN con los datos
embebidos vía `tojson` (sin endpoint JSON).

### Certificados (.p12 → PEM)
pyafipws necesita `.crt` + `.key` PEM separados. `scripts/preparar_certificado.py`
convierte un `.p12` usando la librería `cryptography` (no requiere openssl),
extrae el CUIT del subject del certificado y hace upsert de la `Empresa`. En la
edición web de empresas los certificados son opcionales (solo se reemplaza el
archivo subido).

### PDF + QR (`app/services/pdf_service.py`)
ReportLab arma el comprobante; el **QR fiscal** sigue RG 4892: JSON con datos del
comprobante → base64 → `https://www.afip.gob.ar/fe/qr/?p=<b64>`.

### Web y autenticación (`app/routers/`, `app/auth/`)
Render en servidor (Jinja2 + Bootstrap, `app/web.py` con helper `render()` y
mensajes *flash* en sesión). Auth por cookie de sesión (`SessionMiddleware`).
`get_current_user` lanza `NotAuthenticatedError` → handler global en `main.py`
redirige a `/login`. `require_role(RolUsuario.ADMIN)` protege la gestión de
empresas/certificados.

Convenciones de los ABM (clientes/productos/empresas, mantenerlas al agregar
entidades):
- **Form dual alta/edición**: un solo template con
  `{% set x = entidad if entidad is defined else none %}`; `action` y textos según
  el modo. Rutas: `GET /{id}/editar` + `POST /{id}`.
- **Campos únicos** (`codigo`, `cuit`): `IntegrityError` → `rollback()` + flash de
  advertencia + redirect (nunca dejar el 500).
- **Parámetros opcionales de formularios**: los selects/inputs HTML envían `""`
  (no ausencia). Un query/form param `int | None` con `""` da **422**; declararlo
  `str = ""` y convertir a mano (`int(x) if x.strip().isdigit() else None`). Ver
  `dashboard.index` y `cbte_asociado_id` en facturas.
- El alta de clientes consulta el padrón vía `GET /clientes/consultar-afip`
  (JSON `{ok, ...}` / `{ok: false, error}`; validación→400, conexión/auth→502).

## Convenciones

- Código y comentarios en **español**; PEP 8 (black + ruff).
- **Homologación primero**: validar siempre con `AFIP_MODO=homologacion` (sin
  validez fiscal) antes de producción.
- Nunca versionar `certs/`, `.env`, `logs/`, `pdfs/`, `.afip_cache/` (ver
  `.gitignore`). La base guarda rutas a certificados, nunca su contenido.
