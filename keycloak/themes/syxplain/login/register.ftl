<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=true; section>
    <#if section = "header">
        Create a new account
    <#elseif section = "form">
        <form class="syxplain-form" action="${url.registrationAction}" method="post">
            <div class="syxplain-form-group">
                <label for="firstName" class="syxplain-label">First Name</label>
                <input type="text" id="firstName" name="firstName" class="syxplain-input<#if messagesPerField.existsError('firstName')> input-error</#if>"
                       value="${(register.formData.firstName!'')}" placeholder="First name" autocomplete="given-name">
                <#if messagesPerField.existsError('firstName')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('firstName'))?no_esc}</span>
                </#if>
            </div>

            <div class="syxplain-form-group">
                <label for="lastName" class="syxplain-label">Last Name</label>
                <input type="text" id="lastName" name="lastName" class="syxplain-input<#if messagesPerField.existsError('lastName')> input-error</#if>"
                       value="${(register.formData.lastName!'')}" placeholder="Last name" autocomplete="family-name">
                <#if messagesPerField.existsError('lastName')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('lastName'))?no_esc}</span>
                </#if>
            </div>

            <div class="syxplain-form-group">
                <label for="email" class="syxplain-label">Email</label>
                <input type="email" id="email" name="email" class="syxplain-input<#if messagesPerField.existsError('email')> input-error</#if>"
                       value="${(register.formData.email!'')}" placeholder="your@email.com" autocomplete="email">
                <#if messagesPerField.existsError('email')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('email'))?no_esc}</span>
                </#if>
            </div>

            <#if !realm.registrationEmailAsUsername>
                <div class="syxplain-form-group">
                    <label for="username" class="syxplain-label">Username</label>
                    <input type="text" id="username" name="username" class="syxplain-input<#if messagesPerField.existsError('username')> input-error</#if>"
                           value="${(register.formData.username!'')}" placeholder="Choose a username" autocomplete="username">
                    <#if messagesPerField.existsError('username')>
                        <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('username'))?no_esc}</span>
                    </#if>
                </div>
            </#if>

            <div class="syxplain-form-group">
                <label for="password" class="syxplain-label">Password</label>
                <input type="password" id="password" name="password" class="syxplain-input<#if messagesPerField.existsError('password')> input-error</#if>"
                       placeholder="Enter your password" autocomplete="new-password">
                <#if messagesPerField.existsError('password')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('password'))?no_esc}</span>
                </#if>
            </div>

            <div class="syxplain-form-group">
                <label for="password-confirm" class="syxplain-label">Confirm Password</label>
                <input type="password" id="password-confirm" name="password-confirm" class="syxplain-input<#if messagesPerField.existsError('password-confirm')> input-error</#if>"
                       placeholder="Confirm your password" autocomplete="new-password">
                <#if messagesPerField.existsError('password-confirm')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('password-confirm'))?no_esc}</span>
                </#if>
            </div>

            <button type="submit" class="syxplain-btn-primary">Sign Up</button>

            <div class="syxplain-bottom-link">
                <span>Already have an account? </span>
                <a href="${url.loginUrl}">Sign In</a>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
