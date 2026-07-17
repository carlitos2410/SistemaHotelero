(() => {
        const password = document.querySelector('input[name="password"]');
        const toggle = document.getElementById('password-toggle');
        const form = document.getElementById('login-form');
        const submit = document.getElementById('login-submit');
        const submitText = submit?.querySelector('.login-submit-text');

        toggle?.addEventListener('click', () => {
            const mostrar = password.type === 'password';
            password.type = mostrar ? 'text' : 'password';
            toggle.textContent = mostrar ? 'Ocultar' : 'Ver';
            toggle.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
            toggle.setAttribute('aria-pressed', String(mostrar));
            password.focus();
        });

        form?.addEventListener('submit', () => {
            if (!form.checkValidity()) return;
            submit.disabled = true;
            submit.setAttribute('aria-busy', 'true');
            submitText.textContent = 'Verificando…';
        });
    })();
