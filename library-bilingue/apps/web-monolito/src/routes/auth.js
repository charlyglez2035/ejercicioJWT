const express = require('express');
const bcrypt = require('bcryptjs');
const db = require('../db');
const router = express.Router();

router.get('/login', (req, res) => res.render('auth/login', { title: 'Iniciar sesion' }));
router.post('/login', async (req, res, next) => {
  try {
    const result = await db.query('SELECT user_id, username, password_hash, full_name, role FROM app_user WHERE username = $1 OR email = $1', [req.body.identity]);
    const user = result.rows[0];
    if (!user || !(await bcrypt.compare(req.body.password, user.password_hash))) return res.redirect('/login?error=Credenciales%20invalidas');
    req.session.user = { id: user.user_id, username: user.username, fullName: user.full_name, role: user.role };
    res.redirect('/books?notice=Sesion%20iniciada');
  } catch (error) { next(error); }
});
router.get('/register', (req, res) => res.render('auth/register', { title: 'Crear cuenta' }));
router.post('/register', async (req, res, next) => {
  try {
    const passwordHash = await bcrypt.hash(req.body.password, 12);
    await db.query('INSERT INTO app_user (username, email, password_hash, full_name) VALUES ($1, $2, $3, $4)', [req.body.username, req.body.email, passwordHash, req.body.full_name]);
    res.redirect('/login?notice=Cuenta%20creada');
  } catch (error) { next(error); }
});
router.post('/logout', (req, res) => req.session.destroy(() => res.redirect('/books')));
module.exports = router;
