from django.conf import settings
from django.test import SimpleTestCase


class ConfiguracionSeguridadTests(SimpleTestCase):
    def test_desarrollo_no_acepta_hosts_arbitrarios(self):
        self.assertNotIn('*', settings.ALLOWED_HOSTS)
        self.assertIn('localhost', settings.ALLOWED_HOSTS)
        self.assertIn('testserver', settings.ALLOWED_HOSTS)

    def test_cookies_y_cabeceras_tienen_valores_explicitos(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')

    def test_localhost_no_fuerza_https(self):
        if settings.DJANGO_ENV == 'development':
            self.assertFalse(settings.SECURE_SSL_REDIRECT)
            self.assertFalse(settings.SESSION_COOKIE_SECURE)
            self.assertFalse(settings.CSRF_COOKIE_SECURE)
