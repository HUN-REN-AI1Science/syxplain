<#import "template.ftl" as layout>
<@layout.emailLayout>
    <!-- Warning icon -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td align="center" style="padding-bottom: 20px;">
                <div style="width: 48px; height: 48px; background-color: #fef2f2; border-radius: 50%; text-align: center; line-height: 48px; display: inline-block;">
                    <span style="color: #dc2626; font-size: 22px;">&#9888;</span>
                </div>
            </td>
        </tr>
    </table>

    <h1 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 700; color: #0f172a; line-height: 1.3; text-align: center;">
        Login error detected
    </h1>
    <p style="margin: 0 0 24px 0; font-size: 15px; color: #475569; line-height: 1.6; text-align: center;">
        A failed login attempt was detected on your Syxplain account.
    </p>

    <!-- Details box -->
    <div style="background-color: #fef2f2; border-radius: 8px; padding: 20px; border: 1px solid #fecaca; margin-bottom: 24px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
            <tr>
                <td style="padding: 4px 0; font-size: 13px; color: #64748b; width: 80px; vertical-align: top;">Time</td>
                <td style="padding: 4px 0; font-size: 13px; color: #0f172a; font-weight: 500;">${event.date?datetime?string("yyyy-MM-dd HH:mm:ss z")}</td>
            </tr>
            <tr>
                <td style="padding: 4px 0; font-size: 13px; color: #64748b; vertical-align: top;">IP Address</td>
                <td style="padding: 4px 0; font-size: 13px; color: #0f172a; font-weight: 500; font-family: monospace;">${event.ipAddress}</td>
            </tr>
        </table>
    </div>

    <p style="margin: 0; font-size: 14px; color: #475569; line-height: 1.6;">
        If this was you, no action is needed. If you don't recognize this activity, we recommend changing your password immediately.
    </p>
</@layout.emailLayout>
