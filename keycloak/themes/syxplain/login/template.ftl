<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false showAnotherWayIfPresent=true>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light dark">
    <title>Syxplain AI</title>
    <link rel="icon" type="image/png" href="${url.resourcesPath}/img/syxplain_logo.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="${url.resourcesPath}/css/syxplain.css">
    <style>
        /* Critical layout for the contact footer, inlined because Keycloak serves
           the external CSS with a 30-day cache and an unchanged resource URL —
           browsers with the old stylesheet would otherwise lay the contact block
           out beside the card (flex row) and leave it unstyled. */
        .syxplain-container { flex-direction: column; }
        .syxplain-contact {
            width: 100%;
            max-width: 28rem;
            margin-top: 1.5rem;
            text-align: center;
            font-size: 0.875rem;
            color: var(--color-text-muted, #64748b);
        }
        .syxplain-contact-heading { margin: 0; }
        .syxplain-contact-emails {
            margin-top: 0.25rem;
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: center;
            gap: 0.25rem 0.5rem;
        }
        .syxplain-contact-link {
            color: var(--color-brand-500, #0052cc);
            font-weight: 500;
            text-decoration: none;
        }
        .syxplain-contact-link:hover { text-decoration: underline; }
        .syxplain-contact-sep { color: var(--color-text-muted, #64748b); }
    </style>
</head>
<body>
    <div class="syxplain-container">
        <div class="syxplain-card">
            <div class="syxplain-header">
                <div class="syxplain-logo-circle">
                    <img src="${url.resourcesPath}/img/syxplain_logo.png" alt="Syxplain" class="syxplain-logo-img">
                </div>
                <h1 class="syxplain-title">Syxplain <span class="syxplain-title-ai">AI</span></h1>
                <p class="syxplain-subtitle"><#nested "header"></p>
            </div>

            <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
                <div class="syxplain-alert syxplain-alert-${message.type}">
                    ${kcSanitize(message.summary)?no_esc}
                </div>
            </#if>

            <#nested "form">

            <#if displayInfo>
                <div class="syxplain-info">
                    <#nested "info">
                </div>
            </#if>

            <#if realm.password && social?? && social.providers?has_content>
                <div class="syxplain-social-providers">
                    <div class="syxplain-separator">
                        <span>or</span>
                    </div>
                    <#list social.providers as p>
                        <a href="${p.loginUrl}" class="syxplain-social-btn" id="social-${p.alias}">
                            <#if p.alias == "microsoft">
                                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 21 21" aria-hidden="true">
                                    <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
                                    <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
                                    <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
                                    <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
                                </svg>
                            <#elseif p.alias == "ai4science-login">
                                <img src="${url.resourcesPath}/img/hunren_logo.png" width="18" height="18" alt="" aria-hidden="true" style="object-fit:contain;">
                            <#elseif p.iconClasses?has_content>
                                <i class="${p.iconClasses}"></i>
                            </#if>
                            <span>Sign in with ${p.displayName}</span>
                        </a>
                    </#list>
                </div>
            </#if>
        </div>

        <div class="syxplain-contact">
            <p class="syxplain-contact-heading">Contact the authors</p>
            <p class="syxplain-contact-emails">
                <a href="#" class="syxplain-contact-link" data-e="dWgubmVyLW51aEBkbmFsb3Iuc29sbG9o">[email&#160;protected]</a>
                <span class="syxplain-contact-sep" aria-hidden="true">&middot;</span>
                <a href="#" class="syxplain-contact-link" data-e="dWguYWR1Ym8taW51QGtpcnRhcC5pbHVz">[email&#160;protected]</a>
            </p>
        </div>
    </div>

    <script>
        // Each address is stored base64-encoded AND reversed, so no email-shaped
        // string exists anywhere in the static HTML — not even inside decoded
        // attributes — and no mailto: link is present until the user clicks.
        // Users still see the address and get a single-click mail-client link.
        (function () {
            var links = document.querySelectorAll('.syxplain-contact-link');
            Array.prototype.forEach.call(links, function (a) {
                var addr = atob(a.getAttribute('data-e')).split('').reverse().join('');
                a.textContent = addr;
                a.setAttribute('aria-label', 'Send email to ' + addr);
                a.addEventListener('click', function (e) {
                    e.preventDefault();
                    window.location.href = 'mailto:' + addr;
                });
            });
        })();
    </script>
</body>
</html>
</#macro>
