<#macro emailLayout>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <title>${realmName}</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
</head>
<body style="margin: 0; padding: 0; background-color: #f8f9fc; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;">
    <!-- Outer wrapper -->
    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-color: #f8f9fc;">
        <tr>
            <td align="center" style="padding: 40px 16px;">
                <!-- Inner container -->
                <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width: 560px;">

                    <!-- Logo Header -->
                    <tr>
                        <td align="center" style="padding-bottom: 32px;">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                                <tr>
                                    <td style="width: 48px; height: 48px; background-color: #0052cc; border-radius: 12px; text-align: center; vertical-align: middle;">
                                        <span style="color: #ffffff; font-size: 22px; font-weight: 700; line-height: 48px;">S</span>
                                    </td>
                                    <td style="padding-left: 12px;">
                                        <span style="font-size: 22px; font-weight: 700; color: #0f172a; letter-spacing: -0.5px;">Syxplain</span>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Content Card -->
                    <tr>
                        <td style="background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e5f0; box-shadow: 0 1px 3px rgba(15,23,42,0.05), 0 10px 40px rgba(15,23,42,0.04);">
                            <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                                <tr>
                                    <td style="padding: 40px 36px;">
                                        <#nested>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td align="center" style="padding-top: 32px;">
                            <p style="margin: 0 0 8px 0; font-size: 13px; color: #94a3b8; line-height: 1.5;">
                                Sent by Syxplain &mdash; Neurosymbolic Scientific Discovery
                            </p>
                            <p style="margin: 0; font-size: 12px; color: #cbd5e1; line-height: 1.5;">
                                If you didn't request this email, you can safely ignore it.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
</#macro>
