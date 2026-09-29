const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../../../.env') });
const express = require('express');
const session = require('express-session');
const books = require('./routes/books');
const auth = require('./routes/auth');
const admin = require('./routes/admin');

const app = express();
const port = Number(process.env.PORT || 3000);

app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, '../views'));
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, '../public')));
app.use(session({ secret: process.env.SESSION_SECRET || 'cambia-esta-clave', resave: false, saveUninitialized: false, cookie: { httpOnly: true, sameSite: 'lax' } }));
app.use((req, res, next) => { res.locals.currentUser = req.session.user; res.locals.notice = req.query.notice; res.locals.error = req.query.error; next(); });

app.get('/', (req, res) => res.redirect('/books'));
app.use('/', auth);
app.use('/books', books);
app.use('/admin', admin);
app.use((req, res) => res.status(404).render('error', { title: 'No encontrado', message: 'La pagina solicitada no existe.' }));
app.use((err, req, res, next) => { console.error(err); res.status(500).render('error', { title: 'Error', message: 'No se pudo completar la operacion.' }); });

app.listen(port, () => console.log(`Libreria disponible en http://localhost:${port}`));
