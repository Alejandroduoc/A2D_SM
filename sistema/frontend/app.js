const API_BASE = 'http://localhost:8000/api/v1';
const app = document.querySelector('#app');

const state = {
  token: localStorage.getItem('a2d_access_token'),
  user: JSON.parse(localStorage.getItem('a2d_user') || 'null'),
  users: [],
  loading: false,
};

const icon = (name) => ({
  grid: '▦', users: '♙', trace: '⌁', settings: '⚙', eye: 'Ver', plus: '+',
}[name] || '•');

function initials(name = '') {
  return name.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase() || 'A2';
}

function roleLabel(user) {
  return (user.roles || []).map((role) => role === 'admin' ? 'Administrador' : 'Operador').join(', ') || 'Sin rol';
}

function showAlert(message, type = 'error') {
  const target = document.querySelector('[data-alert]');
  if (!target) return;
  target.className = `alert ${type}`;
  target.textContent = message;
  target.classList.remove('hidden');
}

function clearAlert() {
  const target = document.querySelector('[data-alert]');
  if (target) target.classList.add('hidden');
}

async function readResponse(response, fallbackMessage) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error('No se pudo conectar con la API. Verifica que FastAPI esté ejecutándose en el puerto 8000.');
  }
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || fallbackMessage);
  return result;
}

function renderLogin() {
  app.innerHTML = `
    <main class="login-page">
      <section class="login-visual">
        <div class="brand"><span class="brand-mark">A</span><span>A2D <b>SM</b></span></div>
        <div class="visual-copy">
          <span class="eyebrow">Trazabilidad de planta</span>
          <h1>La operación,<br>en una sola vista.</h1>
          <p>Controla personas, procesos y movimientos con la claridad que exige cada lote.</p>
        </div>
        <div class="visual-footer">PLATAFORMA OPERACIONAL · V 0.1</div>
      </section>
      <section class="login-panel">
        <form class="login-card" data-login-form>
          <span class="eyebrow">Acceso seguro</span>
          <h2>Bienvenido de vuelta</h2>
          <p>Ingresa con tus credenciales para abrir el panel de control.</p>
          <div class="alert hidden" data-alert></div>
          <div class="field"><label for="username">Usuario</label><input id="username" name="username" autocomplete="username" placeholder="Ej. jcontreras" required /></div>
          <div class="field"><label for="password">Contraseña</label><div class="password-wrap"><input id="password" name="password" type="password" autocomplete="current-password" placeholder="Ingresa tu contraseña" required /><button type="button" class="password-toggle" data-toggle-password>Mostrar</button></div></div>
          <button class="primary-btn" type="submit" data-submit>Entrar al panel <span aria-hidden="true">→</span></button>
          <div class="login-hint"><span>¿Es la primera instalación?</span><button type="button" class="text-btn" data-bootstrap>Crear administrador</button></div>
        </form>
      </section>
    </main>`;

  document.querySelector('[data-login-form]').addEventListener('submit', handleLogin);
  document.querySelector('[data-toggle-password]').addEventListener('click', (event) => {
    const input = document.querySelector('#password');
    input.type = input.type === 'password' ? 'text' : 'password';
    event.target.textContent = input.type === 'password' ? 'Mostrar' : 'Ocultar';
  });
  document.querySelector('[data-bootstrap]').addEventListener('click', renderBootstrap);
}

function renderBootstrap() {
  renderLogin();
  const card = document.querySelector('.login-card');
  card.innerHTML = `
    <span class="eyebrow">Primera instalación</span><h2>Crear administrador</h2>
    <p>Este paso solo está disponible mientras la plataforma no tenga usuarios.</p>
    <div class="alert hidden" data-alert></div>
    <div class="field"><label for="full_name">Nombre completo</label><input id="full_name" name="full_name" placeholder="Ej. Javiera Contreras" required /></div>
    <div class="field"><label for="bootstrap_username">Usuario</label><input id="bootstrap_username" name="username" placeholder="Ej. jcontreras" required /></div>
    <div class="field"><label for="bootstrap_password">Contraseña</label><input id="bootstrap_password" name="password" type="password" minlength="8" placeholder="Mínimo 8 caracteres" required /></div>
    <button class="primary-btn" type="button" data-create-admin>Crear cuenta administradora <span aria-hidden="true">→</span></button>
    <div class="login-hint"><span>¿Ya tienes una cuenta?</span><button type="button" class="text-btn" data-back-login>Volver al acceso</button></div>`;
  document.querySelector('[data-create-admin]').addEventListener('click', handleBootstrap);
  document.querySelector('[data-back-login]').addEventListener('click', renderLogin);
}

async function handleLogin(event) {
  event.preventDefault(); clearAlert();
  const button = event.currentTarget.querySelector('[data-submit]');
  button.disabled = true; button.textContent = 'Validando…';
  const data = new FormData(event.currentTarget);
  try {
    const response = await fetch(`${API_BASE}/auth/login`, { method: 'POST', body: new URLSearchParams(data) });
    const result = await readResponse(response, 'No fue posible iniciar sesión.');
    state.token = result.access_token; state.user = result.user;
    localStorage.setItem('a2d_access_token', state.token); localStorage.setItem('a2d_user', JSON.stringify(state.user));
    renderDashboard();
  } catch (error) { showAlert(error.message); button.disabled = false; button.innerHTML = 'Entrar al panel <span aria-hidden="true">→</span>'; }
}

async function handleBootstrap() {
  clearAlert(); const values = Object.fromEntries(new FormData(document.querySelector('.login-card')).entries());
  const button = document.querySelector('[data-create-admin]'); button.disabled = true; button.textContent = 'Creando cuenta…';
  try {
    const response = await fetch(`${API_BASE}/users/bootstrap`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...values, role: 'admin' }) });
    await readResponse(response, 'No fue posible crear el administrador.');
    renderLogin(); showAlert('Administrador creado. Ya puedes ingresar.', 'success');
  } catch (error) { showAlert(error.message); button.disabled = false; button.textContent = 'Crear cuenta administradora →'; }
}

function renderDashboard() {
  app.innerHTML = `
    <div class="app-shell">
      <aside class="sidebar"><div class="brand"><span class="brand-mark">A</span><span>A2D <b>SM</b></span></div>
        <span class="nav-label">Operación</span><button class="nav-item active"><span class="nav-icon">${icon('grid')}</span>Resumen</button><button class="nav-item active" data-users-nav><span class="nav-icon">${icon('users')}</span>Usuarios</button><button class="nav-item"><span class="nav-icon">${icon('trace')}</span>Trazabilidad</button>
        <div class="sidebar-bottom"><div class="user-chip"><span class="avatar">${initials(state.user.full_name)}</span><div><strong>${state.user.full_name}</strong><span>${roleLabel(state.user)}</span></div></div><button class="logout" data-logout>Cerrar sesión</button></div>
      </aside>
      <main class="main"><header class="topbar"><div><h1>Usuarios</h1><p>Administra los accesos y roles de tu planta.</p></div><span class="status-pill"><span class="status-dot"></span> Sistema operativo</span></header>
        <section class="content"><div class="stats"><div class="stat"><span class="stat-label">Usuarios registrados</span><strong class="stat-value" data-total>—</strong><small>Accesos en la plataforma</small></div><div class="stat"><span class="stat-label">Administradores</span><strong class="stat-value" data-admins>—</strong><small>Con permisos de gestión</small></div><div class="stat"><span class="stat-label">Estado de sesión</span><strong class="stat-value" style="font-size:24px">Activa</strong><small>Autenticación JWT</small></div></div>
          <div class="section-head"><div><h2>Directorio de usuarios</h2><p>Consulta y gestiona las cuentas habilitadas.</p></div><button class="outline-btn" data-open-modal><span aria-hidden="true">${icon('plus')}</span> Nuevo usuario</button></div>
          <div class="table-card" data-users-table><div class="empty"><strong>Cargando directorio…</strong><span>Estamos consultando los usuarios registrados.</span></div></div>
        </section>
      </main>
    </div>`;
  document.querySelector('[data-logout]').addEventListener('click', logout);
  document.querySelector('[data-open-modal]').addEventListener('click', renderUserModal);
  loadUsers();
}

async function loadUsers() {
  try {
    const response = await fetch(`${API_BASE}/users`, { headers: { Authorization: `Bearer ${state.token}` } });
    if (response.status === 401 || response.status === 403) return logout();
    const result = await readResponse(response, 'No fue posible cargar los usuarios.');
    state.users = result; renderUsersTable();
  } catch (error) { document.querySelector('[data-users-table]').innerHTML = `<div class="empty"><strong>No se pudo cargar el directorio</strong><span>${error.message}</span></div>`; }
}

function renderUsersTable() {
  const admins = state.users.filter((user) => (user.roles || []).includes('admin')).length;
  document.querySelector('[data-total]').textContent = state.users.length;
  document.querySelector('[data-admins]').textContent = admins;
  const table = state.users.length ? `<div class="table-wrap"><table><thead><tr><th>Persona</th><th>Usuario</th><th>Roles</th><th>Estado</th></tr></thead><tbody>${state.users.map((user) => `<tr><td><div class="person"><span class="avatar">${initials(user.full_name)}</span><div><strong>${user.full_name}</strong><span>Cuenta de acceso</span></div></div></td><td>${user.username}</td><td><span class="role-badge">${roleLabel(user)}</span></td><td><span class="active-badge">● Activo</span></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty"><strong>Aún no hay usuarios</strong><span>Crea la primera cuenta desde el botón de arriba.</span></div>';
  document.querySelector('[data-users-table]').innerHTML = table;
}

function renderUserModal() {
  const modal = document.createElement('div'); modal.className = 'modal-backdrop'; modal.innerHTML = `<form class="modal" data-user-form><div class="modal-head"><div><span class="eyebrow">Directorio</span><h2>Nuevo usuario</h2></div><button type="button" class="close-btn" data-close-modal aria-label="Cerrar">×</button></div><div class="alert hidden" data-alert></div><div class="form-grid"><div class="field"><label>Nombre completo</label><input name="full_name" required placeholder="Ej. Diego Carrillo" /></div><div class="field"><label>Usuario</label><input name="username" required placeholder="Ej. dcarrillo" /></div><div class="field"><label>Correo</label><input name="email" type="email" required placeholder="nombre@empresa.cl" /></div><div class="field"><label>Rol</label><select name="role"><option value="operator">Operador</option><option value="admin">Administrador</option></select></div><div class="field"><label>Contraseña temporal</label><input name="password" type="password" minlength="8" required placeholder="Mínimo 8 caracteres" /></div></div><div class="modal-actions"><button type="button" class="outline-btn" data-close-modal>Cancelar</button><button class="primary-btn" type="submit">Crear usuario</button></div></form>`;
  document.body.appendChild(modal); modal.querySelectorAll('[data-close-modal]').forEach((button) => button.addEventListener('click', () => modal.remove())); modal.querySelector('[data-user-form]').addEventListener('submit', handleCreateUser);
}

async function handleCreateUser(event) {
  event.preventDefault(); clearAlert(); const form = event.currentTarget; const button = form.querySelector('button[type="submit"]'); button.disabled = true; button.textContent = 'Guardando…';
  try { const response = await fetch(`${API_BASE}/users`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${state.token}` }, body: JSON.stringify(Object.fromEntries(new FormData(form).entries())) }); await readResponse(response, 'No fue posible crear el usuario.'); form.closest('.modal-backdrop').remove(); await loadUsers(); } catch (error) { showAlert(error.message); button.disabled = false; button.textContent = 'Crear usuario'; }
}

function logout() { localStorage.removeItem('a2d_access_token'); localStorage.removeItem('a2d_user'); state.token = null; state.user = null; renderLogin(); }

if (state.token && state.user) renderDashboard(); else renderLogin();