from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
import secrets
from werkzeug.utils import secure_filename
from functools import wraps

import psycopg2
import urllib.parse as up

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))

# Configuración para Render
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Credenciales del administrador
ADMIN_CREDENTIALS = {
    'username': os.environ.get('ADMIN_USERNAME', 'admin'),
    'password': os.environ.get('ADMIN_PASSWORD', 'admin123')
}

# Crear carpetas si no existen
for folder in [app.config['UPLOAD_FOLDER'], 'static']:
    if not os.path.exists(folder):
        os.makedirs(folder)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# === REEMPLAZAR ESTA FUNCIÓN COMPLETAMENTE ===
def get_db_connection():
    """Conecta a PostgreSQL en Render o SQLite localmente"""
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # PostgreSQL en Render
        up.uses_netloc.append("postgres")
        url = up.urlparse(database_url)
        conn = psycopg2.connect(
            database=url.path[1:],
            user=url.username,
            password=url.password,
            host=url.hostname,
            port=url.port,
            sslmode='require'
        )
        return conn
    else:
        # SQLite local (desarrollo)
        conn = sqlite3.connect('productos.db')
        return conn

def init_db():
    """Crea la tabla si no existe"""
    conn = get_db_connection()
    
    # Detectar si es PostgreSQL
    if os.environ.get('DATABASE_URL'):
        # PostgreSQL
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id SERIAL PRIMARY KEY,
                nombre VARCHAR(200) NOT NULL,
                descripcion TEXT,
                precio DECIMAL(10,2) NOT NULL,
                categoria VARCHAR(100) NOT NULL,
                disponible BOOLEAN DEFAULT TRUE,
                imagen VARCHAR(255)
            )
        ''')
    else:
        # SQLite
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                precio REAL NOT NULL,
                categoria TEXT NOT NULL,
                disponible INTEGER DEFAULT 1,
                imagen TEXT
            )
        ''')
    
    conn.commit()
    conn.close()

# Decorador para requerir login administrativo
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Por favor inicia sesión como administrador', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ===== RUTAS PÚBLICAS =====
@app.route('/')
def index():
    try:
        search = request.args.get('search', '')
        categoria = request.args.get('categoria', '')
        
        # CAMBIAR ESTA LÍNEA:
        conn = get_db_connection()
        cur = conn.cursor()
        
        if search:
            # CAMBIAR ? POR %s Y agregar tupla
            cur.execute("SELECT * FROM productos WHERE nombre ILIKE %s AND disponible = true", 
                       (f'%{search}%',))
        elif categoria:
            cur.execute("SELECT * FROM productos WHERE categoria = %s AND disponible = true", 
                       (categoria,))
        else:
            cur.execute("SELECT * FROM productos WHERE disponible = true")
        
        productos = cur.fetchall()
        conn.close()
        
        # Obtener categorías únicas
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT categoria FROM productos WHERE disponible = true")
        categorias = [cat[0] for cat in cur.fetchall()]
        conn.close()
        
        return render_template('productos.html', productos=productos, 
                             categorias=categorias, search=search, categoria_seleccionada=categoria)
    except Exception as e:
        return f"Error: {str(e)}", 500

# ===== RUTAS DE ADMINISTRACIÓN =====
@app.route('/admin')
@login_required
def admin():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM productos ORDER BY id DESC")
    productos = cur.fetchall()
    conn.close()
    return render_template('admin.html', productos=productos)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    conn = sqlite3.connect('productos.db')
    c = conn.cursor()
    c.execute("SELECT * FROM productos ORDER BY id DESC")
    productos = c.fetchall()
    conn.close()
    return render_template('admin.html', productos=productos)

@app.route('/admin/agregar_producto', methods=['GET', 'POST'])
@login_required
def agregar_producto():
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            precio = float(request.form['precio'])
            categoria = request.form['categoria']
            # CAMBIAR para PostgreSQL (usa boolean directamente)
            disponible = 'disponible' in request.form  # Esto devuelve True/False
            
            imagen = None
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    imagen = filename
            
            conn = get_db_connection()
            cur = conn.cursor()
            # CAMBIAR ? POR %s
            cur.execute('''INSERT INTO productos 
                        (nombre, descripcion, precio, categoria, disponible, imagen)
                        VALUES (%s, %s, %s, %s, %s, %s)''',
                     (nombre, descripcion, precio, categoria, disponible, imagen))
            conn.commit()
            conn.close()
            
            flash('Producto agregado exitosamente!', 'success')
            return redirect(url_for('admin'))
        
        except Exception as e:
            flash(f'Error al agregar producto: {str(e)}', 'danger')
    
    return render_template('agregar_producto.html')

@app.route('/admin/editar_producto/<int:producto_id>', methods=['GET', 'POST'])
@login_required
def editar_producto(producto_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        try:
            nombre = request.form['nombre']
            descripcion = request.form['descripcion']
            precio = float(request.form['precio'])
            categoria = request.form['categoria']
            # CAMBIAR para PostgreSQL
            disponible = 'disponible' in request.form
            
            imagen = request.form.get('imagen_actual', '')
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    imagen = filename
            
            # CAMBIAR ? POR %s
            cur.execute('''UPDATE productos SET 
                        nombre=%s, descripcion=%s, precio=%s, categoria=%s, disponible=%s, imagen=%s
                        WHERE id=%s''',
                     (nombre, descripcion, precio, categoria, disponible, imagen, producto_id))
            conn.commit()
            conn.close()
            
            flash('Producto actualizado exitosamente!', 'success')
            return redirect(url_for('admin'))
        
        except Exception as e:
            flash(f'Error al actualizar producto: {str(e)}', 'danger')
    
    # CAMBIAR ? POR %s
    cur.execute("SELECT * FROM productos WHERE id=%s", (producto_id,))
    producto = cur.fetchone()
    conn.close()
    
    if not producto:
        flash('Producto no encontrado', 'danger')
        return redirect(url_for('admin'))
    
    return render_template('agregar_producto.html', producto=producto)

@app.route('/admin/eliminar_producto/<int:producto_id>')
@login_required
def eliminar_producto(producto_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # CAMBIAR ? POR %s
        cur.execute("DELETE FROM productos WHERE id=%s", (producto_id,))
        conn.commit()
        conn.close()
        
        flash('Producto eliminado exitosamente!', 'success')
    except Exception as e:
        flash(f'Error al eliminar producto: {str(e)}', 'danger')
    
    return redirect(url_for('admin'))

# Ruta de prueba para verificar que la app funciona
@app.route('/health')
def health():
    return 'La aplicación está funcionando correctamente!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)