import os

TEMPLATES_DIR = os.path.join(
    os.path.dirname(__file__),
    '..', 'Spam-Detection-Classifier-main',
    'Spam-Detection-Classifier-main', 'spam_detection',
    'detector', 'templates'
)

# Navbar HTML to inject — uses Django {% url %} tags so active state works
NAVBAR = '''    <!-- Unified Navbar -->
    <nav class="navbar navbar-expand-lg navbar-dark gradient-bg" style="box-shadow:0 2px 10px rgba(0,0,0,0.15)">
        <div class="container-fluid px-4">
            <a class="navbar-brand fw-bold" href="{% url 'home' %}">
                <i class="fas fa-shield-alt me-2"></i>SpamShield AI
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarMain">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarMain">
                <ul class="navbar-nav ms-auto align-items-center gap-1">
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'home' %}">
                            <i class="fas fa-home me-1"></i>Home
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'model_metrics' %}">
                            <i class="fas fa-chart-line me-1"></i>Metrics
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'blocked_emails' %}">
                            <i class="fas fa-ban me-1"></i>Blocked
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'real_time_alerts' %}">
                            <i class="fas fa-bell me-1"></i>Alerts
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'alert_settings' %}">
                            <i class="fas fa-cog me-1"></i>Settings
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'powerbi_export' %}">
                            <i class="fas fa-file-export me-1"></i>Export
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="{% url 'documentation' %}">
                            <i class="fas fa-book me-1"></i>Docs
                        </a>
                    </li>
                    <li class="nav-item ms-2">
                        <a class="nav-link" href="/"
                           style="background:rgba(231,76,60,0.3);border:1px solid rgba(231,76,60,0.5);border-radius:6px;padding:6px 14px;color:#ffc9c9">
                            <i class="fas fa-sign-out-alt me-1"></i>Logout
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>
'''

# Old navbar patterns to replace (each template has a slightly different one)
OLD_NAV_START = '<nav class="navbar navbar-expand-lg navbar-dark gradient-bg">'
OLD_NAV_END   = '</nav>'

templates = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.html')]

for filename in templates:
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find and replace the old navbar block
    start_idx = content.find(OLD_NAV_START)
    if start_idx == -1:
        print(f'  SKIP (no navbar found): {filename}')
        continue

    end_idx = content.find(OLD_NAV_END, start_idx)
    if end_idx == -1:
        print(f'  SKIP (no closing nav): {filename}')
        continue

    end_idx += len(OLD_NAV_END)
    new_content = content[:start_idx] + NAVBAR + content[end_idx:]

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f'  UPDATED: {filename}')

print('\nDone! All spam detection templates updated with unified navbar.')
