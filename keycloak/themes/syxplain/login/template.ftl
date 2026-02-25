<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false showAnotherWayIfPresent=true>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Syxplain AI</title>
    <link rel="stylesheet" href="${url.resourcesPath}/css/syxplain.css">
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
                            <#if p.iconClasses?has_content>
                                <i class="${p.iconClasses}"></i>
                            </#if>
                            <span>Sign in with ${p.displayName}</span>
                        </a>
                    </#list>
                </div>
            </#if>
        </div>
    </div>
</body>
</html>
</#macro>
