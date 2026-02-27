<#import "template.ftl" as layout>
<@layout.emailLayout>
    <!-- Check icon -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr>
            <td align="center" style="padding-bottom: 20px;">
                <div style="width: 48px; height: 48px; background-color: #ecfdf5; border-radius: 50%; text-align: center; line-height: 48px; display: inline-block;">
                    <span style="color: #059669; font-size: 22px;">&#10003;</span>
                </div>
            </td>
        </tr>
    </table>

    <h1 style="margin: 0 0 8px 0; font-size: 22px; font-weight: 700; color: #0f172a; line-height: 1.3; text-align: center;">
        Email configuration working
    </h1>
    <p style="margin: 0; font-size: 15px; color: #475569; line-height: 1.6; text-align: center;">
        This is a test email from Syxplain. If you're reading this, your email settings are configured correctly.
    </p>
</@layout.emailLayout>
