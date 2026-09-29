import json
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from tkinter import END, BooleanVar, StringVar, Tk, Toplevel, Text, filedialog, messagebox
from tkinter import ttk


JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
SECRET_KEY_PATTERN = re.compile(r"(authorization|cookie|password|token|secret|api[-_]?key|credential)", re.I)


def sanitize(value, key=""):
    if SECRET_KEY_PATTERN.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {name: sanitize(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return JWT_PATTERN.sub("[REDACTED]", value)
    return value


def sanitize_url(value):
    try:
        parts = urllib.parse.urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        if parts.username or parts.password:
            host = f"[REDACTED]@{host}"
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query = [
            (key, "[REDACTED]" if SECRET_KEY_PATTERN.search(key) else item)
            for key, item in query
        ]
        return urllib.parse.urlunsplit((parts.scheme, host, parts.path,
                                        urllib.parse.urlencode(query), parts.fragment))
    except (TypeError, ValueError):
        return JWT_PATTERN.sub("[REDACTED]", value)


class LibraryClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Library | Cliente JWT")
        self.root.geometry("1040x760")
        self.token = None
        self.results = queue.Queue()
        self.login_url = StringVar(value="http://127.0.0.1:5000")
        self.books_url = StringVar(value="http://127.0.0.1:5001")
        self.identity = StringVar()
        self.password = StringVar()
        self.isbn = StringVar()
        self.method = StringVar(value="GET")
        self.without_token = BooleanVar(value=False)
        self.status = StringVar(value="JWT en memoria: no")
        self._build()
        self.root.after(100, self._poll_results)

    def _build(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(3, weight=1)
        urls = ttk.LabelFrame(self.root, text="Servicios")
        urls.grid(row=0, column=0, sticky="ew", padx=12, pady=10)
        urls.columnconfigure(1, weight=1)
        urls.columnconfigure(3, weight=1)
        ttk.Label(urls, text="Login").grid(row=0, column=0, padx=8, pady=8)
        ttk.Entry(urls, textvariable=self.login_url).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(urls, text="Book").grid(row=0, column=2, padx=8)
        ttk.Entry(urls, textvariable=self.books_url).grid(row=0, column=3, sticky="ew", padx=8)

        auth = ttk.LabelFrame(self.root, text="Autenticacion")
        auth.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        auth.columnconfigure(1, weight=1)
        auth.columnconfigure(3, weight=1)
        ttk.Label(auth, text="Usuario o correo").grid(row=0, column=0, padx=8, pady=8)
        ttk.Entry(auth, textvariable=self.identity).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Label(auth, text="Contrasena").grid(row=0, column=2, padx=8)
        ttk.Entry(auth, textvariable=self.password, show="*").grid(row=0, column=3, sticky="ew", padx=8)
        ttk.Button(auth, text="Registro", command=self._registration_dialog).grid(row=0, column=4, padx=6)
        ttk.Button(auth, text="Login", command=self._login).grid(row=0, column=5, padx=6)
        ttk.Button(auth, text="Session", command=self._session).grid(row=0, column=6, padx=6)
        ttk.Button(auth, text="Logout", command=self._logout).grid(row=0, column=7, padx=8)
        ttk.Label(auth, textvariable=self.status).grid(row=1, column=0, columnspan=8, sticky="w", padx=8, pady=(0, 8))

        request = ttk.LabelFrame(self.root, text="Servicio book")
        request.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        ttk.Label(request, text="Metodo").grid(row=0, column=0, padx=(8, 4), pady=8)
        ttk.Combobox(request, textvariable=self.method, values=("GET", "POST", "PUT", "PATCH", "DELETE"), state="readonly", width=9).grid(row=0, column=1, padx=4)
        ttk.Label(request, text="ISBN").grid(row=0, column=2, padx=(12, 4))
        ttk.Entry(request, textvariable=self.isbn, width=24).grid(row=0, column=3, padx=4)
        ttk.Button(request, text="Consultar", command=self._public_get).grid(row=0, column=4, padx=6)
        ttk.Checkbutton(request, text="Omitir JWT", variable=self.without_token).grid(row=0, column=5, padx=8)
        ttk.Button(request, text="Enviar CRUD", command=self._book_request).grid(row=0, column=6, padx=8)
        ttk.Label(request, text="Payload JSON").grid(row=1, column=0, sticky="nw", padx=8)
        self.payload = Text(request, height=7, wrap="none", font=("Consolas", 10))
        self.payload.grid(row=1, column=1, columnspan=6, sticky="ew", padx=8, pady=(0, 8))
        self.payload.insert("1.0", '{\n  "isbn": "978-0000000000",\n  "title": "Libro temporal JWT",\n  "publication_year": 2026,\n  "price": 10.00,\n  "stock": 1,\n  "format_id": 1,\n  "category_id": 1,\n  "authors": []\n}')
        request.columnconfigure(6, weight=1)

        log_frame = ttk.LabelFrame(self.root, text="Peticiones sanitizadas")
        log_frame.grid(row=3, column=0, sticky="nsew", padx=12, pady=8)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = Text(log_frame, wrap="none", state="disabled", font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)
        actions = ttk.Frame(log_frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        ttk.Button(actions, text="Copiar", command=self._copy_log).pack(side="left", padx=4)
        ttk.Button(actions, text="Exportar", command=self._export_log).pack(side="left", padx=4)
        ttk.Button(actions, text="Limpiar", command=self._clear_log).pack(side="left", padx=4)

    def _registration_dialog(self):
        dialog = Toplevel(self.root)
        dialog.title("Registro de usuario")
        fields = ("username", "email", "nombre", "apellido_paterno", "apellido_materno", "password")
        inputs = {}
        for row, name in enumerate(fields):
            ttk.Label(dialog, text=name.replace("_", " ")).grid(row=row, column=0, padx=8, pady=5, sticky="w")
            entry = ttk.Entry(dialog, show="*" if name == "password" else "", width=34)
            entry.grid(row=row, column=1, padx=8, pady=5, sticky="ew")
            inputs[name] = entry

        def register():
            values = {name: field.get() for name, field in inputs.items()}
            self._request(
                "login", "POST", self._service_url(self.login_url.get(), "/register?format=json"),
                values, action="register", include_token=False
            )
            dialog.destroy()

        ttk.Button(dialog, text="Registrar", command=register).grid(row=len(fields), column=1, padx=8, pady=10, sticky="e")
        dialog.columnconfigure(1, weight=1)

    def _service_url(self, base, path):
        return base.rstrip("/") + path

    def _login(self):
        if not self.identity.get().strip() or not self.password.get():
            messagebox.showinfo("Login", "Captura usuario/correo y contrasena.")
            return
        self._request("login", "POST", self._service_url(self.login_url.get(), "/login?format=json"), {
            "identity": self.identity.get().strip(), "password": self.password.get()
        }, action="login", include_token=False)

    def _session(self):
        self._request("login", "GET", self._service_url(self.login_url.get(), "/session?format=json"), action="session")

    def _logout(self):
        self._request("login", "POST", self._service_url(self.login_url.get(), "/logout?format=json"), action="logout")

    def _public_get(self):
        isbn = self.isbn.get().strip()
        path = f"/api/books/{urllib.parse.quote(isbn)}?format=json" if isbn else "/api/books?format=json"
        self._request("book", "GET", self._service_url(self.books_url.get(), path), include_token=False)

    def _book_request(self):
        method = self.method.get()
        isbn = self.isbn.get().strip()
        if method == "POST":
            path = "/api/books?format=json"
        elif not isbn:
            messagebox.showinfo("ISBN requerido", "Captura el ISBN para esta operacion.")
            return
        else:
            path = f"/api/books/{urllib.parse.quote(isbn)}?format=json"

        payload = None
        if method not in ("GET", "DELETE"):
            try:
                payload = json.loads(self.payload.get("1.0", END))
                if not isinstance(payload, dict):
                    raise ValueError("El payload debe ser un objeto JSON.")
            except (json.JSONDecodeError, ValueError) as error:
                messagebox.showerror("Payload invalido", str(error))
                return
        self._request("book", method, self._service_url(self.books_url.get(), path), payload,
                      include_token=not self.without_token.get())

    def _request(self, service, method, url, payload=None, action=None, include_token=True):
        request_id = str(uuid.uuid4())
        headers = {"Accept": "application/json", "X-Request-ID": request_id}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if include_token and self.token:
            headers["Authorization"] = "Bearer " + self.token
        safe_headers = sanitize(headers)
        safe_payload = sanitize(payload)

        def worker():
            started = datetime.now().timestamp()
            status = None
            response_data = None
            new_token = None
            error = None
            data = json.dumps(payload).encode("utf-8") if payload is not None else None
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
                    raw = response.read(1_000_000).decode("utf-8", errors="replace")
            except urllib.error.HTTPError as response:
                status = response.code
                raw = response.read(1_000_000).decode("utf-8", errors="replace")
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exception:
                raw = ""
                error = str(exception)
            try:
                response_data = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                response_data = raw
            if action == "login" and isinstance(response_data, dict):
                new_token = response_data.get("access_token")
            elapsed_ms = round((datetime.now().timestamp() - started) * 1000, 2)
            record = {
                "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
                "request_id": request_id,
                "servicio": service,
                "metodo": method,
                "url": sanitize_url(url),
                "headers": safe_headers,
                "payload": safe_payload,
                "estado_http": status,
                "duracion_ms": elapsed_ms,
                "respuesta": sanitize(response_data),
                "error": sanitize(error),
            }
            self.results.put((record, action, status, new_token))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_results(self):
        while True:
            try:
                record, action, status, new_token = self.results.get_nowait()
            except queue.Empty:
                break
            if action == "login" and status is not None and status < 300 and new_token:
                self.token = new_token
                self.status.set("JWT en memoria: si")
                self.password.set("")
            elif action == "logout" or status == 401:
                self.token = None
                self.status.set("JWT en memoria: no")
            self.log.configure(state="normal")
            self.log.insert(END, json.dumps(record, ensure_ascii=False, indent=2) + "\n\n")
            lines = int(self.log.index("end-1c").split(".")[0])
            if lines > 4000:
                self.log.delete("1.0", f"{lines - 4000}.0")
            self.log.see(END)
            self.log.configure(state="disabled")
        self.root.after(100, self._poll_results)

    def _copy_log(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log.get("1.0", END))

    def _export_log(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=(("Text", "*.txt"),))
        if path:
            with open(path, "w", encoding="utf-8") as output:
                output.write(self.log.get("1.0", END))

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", END)
        self.log.configure(state="disabled")


if __name__ == "__main__":
    root = Tk()
    LibraryClient(root)
    root.mainloop()