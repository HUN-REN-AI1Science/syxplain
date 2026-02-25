<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('password','password-confirm'); section>
    <#if section = "header">
        Set a new password
    <#elseif section = "form">
        <form class="syxplain-form" action="${url.loginAction}" method="post">
            <input type="text" id="username" name="username" value="${username}" autocomplete="username" readonly="readonly" style="display:none;">

            <div class="syxplain-form-group">
                <label for="password-new" class="syxplain-label">New Password</label>
                <input type="password" id="password-new" name="password-new" class="syxplain-input<#if messagesPerField.existsError('password')> input-error</#if>"
                       placeholder="Enter new password" autofocus autocomplete="new-password">
                <#if messagesPerField.existsError('password')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('password'))?no_esc}</span>
                </#if>
            </div>

            <div class="syxplain-form-group">
                <label for="password-confirm" class="syxplain-label">Confirm Password</label>
                <input type="password" id="password-confirm" name="password-confirm" class="syxplain-input<#if messagesPerField.existsError('password-confirm')> input-error</#if>"
                       placeholder="Confirm new password" autocomplete="new-password">
                <#if messagesPerField.existsError('password-confirm')>
                    <span class="syxplain-field-error">${kcSanitize(messagesPerField.getFirstError('password-confirm'))?no_esc}</span>
                </#if>
            </div>

            <button type="submit" class="syxplain-btn-primary">Update Password</button>
        </form>
    </#if>
</@layout.registrationLayout>
