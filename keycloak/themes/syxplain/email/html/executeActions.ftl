<#import "template.ftl" as layout>
<@layout.emailLayout>
    <h1 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 700; color: #0f172a; line-height: 1.3;">
        Update your account
    </h1>
    <p style="margin: 0 0 20px 0; font-size: 15px; color: #475569; line-height: 1.6;">
        Your Syxplain account requires the following action<#if requiredActions?size gt 1>s</#if>:
    </p>

    <!-- Actions list -->
    <div style="background-color: #f8f9fc; border-radius: 8px; padding: 16px 20px; border: 1px solid #e2e5f0; margin-bottom: 28px;">
        <#list requiredActions as reqActionItem>
            <div style="padding: 6px 0; font-size: 14px; color: #0f172a; <#if reqActionItem_has_next>border-bottom: 1px solid #e2e5f0; margin-bottom: 6px;</#if>">
                <span style="color: #0052cc; margin-right: 8px;">&#9679;</span>
                ${msg("requiredAction.${reqActionItem}")}
            </div>
        </#list>
    </div>

    <!-- CTA Button -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td align="center" style="padding-bottom: 28px;">
                <a href="${link}" target="_blank" style="display: inline-block; background-color: #0052cc; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; padding: 12px 32px; border-radius: 8px; line-height: 1.4;">
                    Complete Action<#if requiredActions?size gt 1>s</#if>
                </a>
            </td>
        </tr>
    </table>

    <p style="margin: 0 0 16px 0; font-size: 13px; color: #94a3b8; line-height: 1.5;">
        This link will expire in ${linkExpiration}.
    </p>

    <!-- Fallback link -->
    <div style="background-color: #f8f9fc; border-radius: 8px; padding: 16px; border: 1px solid #e2e5f0;">
        <p style="margin: 0 0 8px 0; font-size: 12px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
            Or copy this link
        </p>
        <p style="margin: 0; font-size: 13px; word-break: break-all;">
            <a href="${link}" style="color: #0052cc; text-decoration: none;">${link}</a>
        </p>
    </div>
</@layout.emailLayout>
