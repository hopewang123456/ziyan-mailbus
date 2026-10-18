package io.github.hopewang123456.mailbus.adapters.notify;

import io.github.hopewang123456.mailbus.ports.Notifier;
import jakarta.mail.Authenticator;
import jakarta.mail.Message;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.Properties;

/**
 * SMTP channel (python smtp counterpart): config-driven
 * (mailbus.notify.smtp.{host,port,from,to,username,password,starttls});
 * empty host disables. Levels filter per python semantics — CRITICAL and
 * INFO-digest by default (mail is high-friction).
 */
public class SmtpNotifier implements Notifier {

    private final String host;
    private final int port;
    private final String from;
    private final String to;
    private final String user;
    private final String pass;
    private final boolean starttls;

    public SmtpNotifier(String host, int port, String from, String to,
                        String user, String pass, boolean starttls) {
        this.host = host == null ? "" : host;
        this.port = port;
        this.from = from;
        this.to = to;
        this.user = user;
        this.pass = pass;
        this.starttls = starttls;
    }

    public boolean enabled() {
        return !host.isBlank() && from != null && !from.isBlank() && to != null && !to.isBlank();
    }

    @Override
    public void notify(Level level, String title, String body) {
        if (!enabled() || level == Level.WARN) {
            return; // mail stays for critical + digest traffic
        }
        try {
            Properties props = new Properties();
            props.put("mail.smtp.host", host);
            props.put("mail.smtp.port", String.valueOf(port));
            props.put("mail.smtp.auth", String.valueOf(user != null && !user.isBlank()));
            if (starttls) {
                props.put("mail.smtp.starttls.enable", "true");
            }
            Session session = Session.getInstance(props, new Authenticator() {
                @Override
                protected PasswordAuthentication getPasswordAuthentication() {
                    return user == null || user.isBlank() ? null
                            : new PasswordAuthentication(user, pass);
                }
            });
            MimeMessage msg = new MimeMessage(session);
            msg.setFrom(new InternetAddress(from));
            msg.setRecipients(Message.RecipientType.TO, InternetAddress.parse(to));
            msg.setSubject("[mailbus-j " + level + "] " + title);
            msg.setText(body == null ? "" : body, "UTF-8");
            Transport.send(msg);
        } catch (Exception ignored) {
            // per-channel isolation: smtp outages never break the patrol loop
        }
    }
}
