function requireAuth(req, res, next) {
  if (!req.session.user) return res.redirect('/login?error=Inicia%20sesion%20para%20continuar');
  next();
}

function requireAdmin(req, res, next) {
  if (!req.session.user || req.session.user.role !== 'admin') return res.status(403).render('error', { title: 'Acceso denegado', message: 'Necesitas permisos de administrador.' });
  next();
}

module.exports = { requireAuth, requireAdmin };
