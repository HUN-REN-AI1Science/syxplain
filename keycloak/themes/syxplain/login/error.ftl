<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=true; section>
    <#if section = "header">
        Something went wrong
    <#elseif section = "form">
        <div class="syxplain-info" style="margin-top: 0; margin-bottom: 1rem;">
            <#if message?has_content>
                ${kcSanitize(message.summary)?no_esc}
            </#if>
        </div>

        <#if skipLink??>
        <#else>
            <#if client?? && client.baseUrl?has_content>
                <a href="${client.baseUrl}" class="syxplain-btn-primary" style="display: block; text-align: center; text-decoration: none; line-height: 48px;">Back to Application</a>
            </#if>
        </#if>
    </#if>
</@layout.registrationLayout>
