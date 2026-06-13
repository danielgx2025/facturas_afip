# Sistema Web de Facturación Electrónica AFIP

Sistema web (FastAPI + SQLAlchemy + Jinja2) para emitir comprobantes
electrónicos de AFIP (Argentina) usando [pyafipws](https://github.com/reingart/pyafipws):
facturas **A/B/C** y **notas de crédito/débito** vía **WSFEv1**, con generación
de **PDF + QR fiscal**, **multiempresa** (varios CUIT) y **login por roles**.

> ⚠️ Trabajá **siempre primero en homologación** (entorno de pruebas, sin validez
> fiscal). Recién cuando todo funcione, pasá a producción.

---

## 1. Arquitectura

```
app/
├── afip/         Capa de integración AFIP (WSAA + WSFEv1) — núcleo aislado
├── models/       Modelos ORM SQLAlchemy
├── services/     Lógica de negocio (facturación, numeración, PDF)
├── routers/      Endpoints web (auth, empresas, clientes, productos, facturas)
├── auth/         Hashing de contraseñas + dependencias de roles
├── templates/    Vistas Jinja2 + Bootstrap
├── config.py     Configuración tipada desde .env
├── database.py   Engine / sesión SQLAlchemy
└── main.py       App FastAPI
scripts/
├── init_db.py                  Crea tablas + admin + empresa demo
└── emitir_factura_ejemplo.py   Script CLI: emite una Factura B de ejemplo
```

| Componente | Archivo |
|------------|---------|
| Autenticación WSAA (Token/Sign, cache del TA) | [app/afip/wsaa_client.py](app/afip/wsaa_client.py) |
| Emisión WSFEv1 (CAE, facturas, NC/ND)         | [app/afip/wsfe_client.py](app/afip/wsfe_client.py) |
| Orquestación de la emisión                     | [app/services/facturacion.py](app/services/facturacion.py) |
| PDF + QR fiscal                                | [app/services/pdf_service.py](app/services/pdf_service.py) |

---

## 2. Requisitos

- **Python 3.11+**
- **MySQL 8** corriendo en `localhost` (usuario `root`, según `.env`)
- Certificado digital de AFIP (`.crt`) y su clave privada (`.key`)

---

## 3. Instalación

```powershell
# 1. (Opcional) crear y activar un entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar dependencias base
pip install -r requirements.txt

# 3. Instalar pyafipws (versión Python 3) APARTE y sin dependencias.
#    Requiere git instalado. Ver la nota de abajo sobre por qué --no-deps.
pip install --no-deps git+https://github.com/reingart/pyafipws.git

# 4. Verificar que pyafipws importe sin error
python -c "from pyafipws.wsaa import WSAA; from pyafipws.wsfev1 import WSFEv1; print('pyafipws OK')"
```

> **Por qué pyafipws se instala aparte:** la versión de PyPI (`PyAfipWs`) es
> **Python 2** y no funciona en Python 3. La versión Python 3 está en el repo de
> GitHub, pero sus dependencias fijadas (`Pillow<=9.5.0`, `cryptography==41`,
> `qrcode==6.1`) **rompen en Python 3.13**, por eso `--no-deps`: sus dependencias
> de runtime (`future`, `pysimplesoap==1.8.22`, `httplib2`, `certifi`,
> `setuptools<74`) ya están en `requirements.txt`.
>
> **Nota Python 3.12+ / `distutils`:** `pysimplesoap` importa `distutils`, que se
> removió de la stdlib. Por eso fijamos `setuptools<74`, que restituye el shim de
> `distutils` automáticamente al arrancar el intérprete.

Crear la base de datos en MySQL:

```sql
CREATE DATABASE facturas_afip CHARACTER SET utf8mb4;
```

Configurar el entorno:

```powershell
Copy-Item .env.example .env
# Editar .env: completar DB_PASSWORD, SECRET_KEY (generala con el comando de abajo)
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Inicializar el esquema y el usuario administrador:

```powershell
python scripts/init_db.py
```

Registrar la empresa emisora a partir de un certificado `.p12` (PKCS#12, que
contiene cert + clave juntos). Extrae el `.crt`/`.key` a `certs/` y crea la
empresa con su CUIT (leído del certificado) y un punto de venta:

```powershell
python scripts/preparar_certificado.py --p12 "ruta\al\certificado.p12"
# Si el .p12 tiene contraseña:  --password TU_CLAVE
```

---

## 4. Gestión de certificados (.crt / .key) — seguridad

Los certificados **no se versionan** y viven en la carpeta `certs/`
(ignorada por git). La base de datos solo guarda la **ruta** al archivo.

### Generar la clave y el pedido de certificado (CSR)

```bash
# 1) Clave privada (queda solo en tu poder)
openssl genrsa -out 20111111112.key 2048

# 2) Pedido de certificado (CSR) con tu CUIT
openssl req -new -key 20111111112.key \
  -subj "/C=AR/O=Tu Razon Social/CN=facturador/serialNumber=CUIT 20111111112" \
  -out 20111111112.csr
```

### Obtener y asociar el certificado en AFIP

1. **Homologación:** subí el `.csr` en el servicio **WSASS**
   (*Autogestión de Certificados Homologación*) y descargá el `.crt`.
   **Producción:** usá *"Administración de Certificados Digitales"* con Clave Fiscal.
2. **Asociá** el certificado al web service **`wsfe`** y **delegá** la relación
   al CUIT en el *"Administrador de Relaciones de Clave Fiscal"*.
3. Guardá `20111111112.crt` y `20111111112.key` en `certs/` (o subilos desde la
   pantalla de **Empresas** del sistema, que los guarda con ese nombre).

### Buenas prácticas

- `.gitignore` ya ignora `certs/`, `*.key`, `*.crt`, `.env`, `logs/`, `pdfs/`.
- Permisos restrictivos sobre la clave privada:
  - Windows: `icacls 20111111112.key /inheritance:r /grant:r "%USERNAME%:R"`
  - Linux/macOS: `chmod 600 20111111112.key`
- Nunca compartas ni subas la `.key`. Si se filtra, **revocá y regenerá**.
- En producción, considerá montar `certs/` desde un volumen o *secret manager*.

---

## 5. Probar en homologación

### A) Prueba CLI (recomendada primero)

```powershell
python scripts/emitir_factura_ejemplo.py
```

Debe imprimir `Resultado: A`, un **CAE** y su vencimiento. Valida toda la cadena
(WSAA → WSFEv1 → CAE → PDF) antes de usar la web.

### B) Aplicación web

```powershell
uvicorn app.main:app --reload
```

Abrí <http://localhost:8000>, ingresá con el usuario admin del `.env`, y:

1. **Empresas** → cargá tu empresa y subí el `.crt`/`.key`.
2. **Clientes** y **Productos** → cargá algunos registros.
3. **Comprobantes → Emitir** → elegí empresa, cliente, tipo y productos →
   *Emitir y solicitar CAE*.
4. Descargá el **PDF** (incluye el **QR fiscal**) desde el listado.

### C) Prueba de humo automatizada (opcional)

```powershell
pytest -s tests/test_afip_homologacion.py
```

---

## 6. Pasar a producción

1. En `.env`, cambiar `AFIP_MODO=produccion`.
2. Usar el **certificado de producción** y un **punto de venta habilitado**
   para facturación electrónica (tipo "Web Services").
3. Generar una clave `SECRET_KEY` nueva y fuerte; servir por **HTTPS**.

Recién en producción los **CAE tienen validez fiscal**.

---

## 7. Manejo de errores y logs

- Las llamadas a AFIP se registran en `logs/afip.log` (rotativo).
- Excepciones propias en [app/afip/exceptions.py](app/afip/exceptions.py):
  `AfipAuthError` (certificado/relación), `AfipValidationError` (rechazo de AFIP
  con detalle de errores/observaciones) y `AfipConnectionError` (red/WSDL).
- En la web, los errores se muestran como mensajes *flash*; el detalle técnico
  queda en el log.

---

## 8. Notas / ajustes posibles

- **Condición IVA del receptor (RG 5616):** es **obligatoria** y ya está
  implementada. La condición del cliente (texto) se mapea al id de AFIP en
  [app/afip/constants.py](app/afip/constants.py) (`condicion_iva_receptor_id`) y
  se envía en `CrearFactura`. Mapeo actual: Consumidor Final→5, Responsable
  Inscripto→1, Monotributo→6, Exento→4 (default: Consumidor Final).
- La numeración la asigna AFIP (`CompUltimoAutorizado + 1`); no se reserva
  localmente para evitar saltos.
- **Contraseñas:** se hashean con `bcrypt` directamente (no `passlib`, que quedó
  sin mantenimiento y es incompatible con bcrypt moderno).
