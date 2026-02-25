<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username'); section>
    <#if section = "header">
        Enter your email to reset your password
    <#elseif section = "form">
        <form class="syxplain-form" action="${url.loginAction}" method="post">
            <div class="syxplain-form-group">
                <label for="username" class="syxplain-label">Email</label>
                <input type="text" id="username" name="username" class="syxplain-input<#if messagesPerField.existsError('username')> input-error</#if>"
                       value="${(auth.attemptedUsername!'')}" placeholder="your@email.com" autofocus autocomplete="email">
                <#if messagesPerField.existsError('username')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('username'))?no_esc}</span>
                </#if>
            </div>

            <button type="submit" class="syxplain-btn-primary">Send Reset Link</button>

            <div class="syxplain-back-link">
                <a href="${url.loginUrl}">Back to Login</a>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
