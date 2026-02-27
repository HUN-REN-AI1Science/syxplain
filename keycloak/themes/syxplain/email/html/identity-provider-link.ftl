<#import "template.ftl" as layout>
<@layout.emailLayout>
    <h1 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 700; color: #0f172a; line-height: 1.3;">
        Link your account
    </h1>
    <p style="margin: 0 0 28px 0; font-size: 15px; color: #475569; line-height: 1.6;">
        Someone wants to link your <strong style="color: #0f172a;">${identityProviderAlias}</strong> account with your Syxplain account. If this was you, click the button below to confirm the link.
    </p>

    <!-- CTA Button -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td align="center" style="padding-bottom: 28px;">
                <a href="${link}" target="_blank" style="display: inline-block; background-color: #0052cc; color: #ffffff; font-size: 15px; font-weight: 600; text-decoration: none; padding: 12px 32px; border-radius: 8px; line-height: 1.4;">
                    Link Accounts
                </a>
            </td>
        </tr>
    </table>

    <p style="margin: 0 0 16px 0; font-size: 13px; color: #94a3b8; line-height: 1.5;">
        This link will expire in ${linkExpiration}. If you didn't request this, you can safely ignore this email.
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
