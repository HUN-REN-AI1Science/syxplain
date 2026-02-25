<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username','password') displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??; section>
    <#if section = "header">
        Sign in to your account
    <#elseif section = "form">
        <form class="syxplain-form" action="${url.loginAction}" method="post">
            <div class="syxplain-form-group">
                <label for="username" class="syxplain-label">Email</label>
                <input type="text" id="username" name="username" class="syxplain-input<#if messagesPerField.existsError('username','password')> input-error</#if>"
                       value="${(login.username!'')}" placeholder="your@email.com" autofocus autocomplete="email">
                <#if messagesPerField.existsError('username','password')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}</span>
                </#if>
            </div>

            <div class="syxplain-form-group">
                <label for="password" class="syxplain-label">Password</label>
                <input type="password" id="password" name="password" class="syxplain-input<#if messagesPerField.existsError('username','password')> input-error</#if>"
                       placeholder="Enter your password" autocomplete="current-password">
                <#if realm.resetPasswordAllowed>
                    <div class="syxplain-forgot-password">
                        <a href="${url.loginResetCredentialsUrl}">Forgot Password?</a>
                    </div>
                </#if>
            </div>

            <input type="hidden" id="id-hidden-input" name="credentialId" <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>>

            <button type="submit" class="syxplain-btn-primary">Sign In</button>
        </form>
    <#elseif section = "info">
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div class="syxplain-bottom-link">
                <span>Don't have an account? </span>
                <a href="${url.registrationUrl}">Sign Up</a>
            </div>
        </#if>
    </#if>
</@layout.registrationLayout>
