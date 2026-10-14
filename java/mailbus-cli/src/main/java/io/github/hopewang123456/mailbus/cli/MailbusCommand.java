package io.github.hopewang123456.mailbus.cli;

import io.github.hopewang123456.mailbus.app.InboxService;
import io.github.hopewang123456.mailbus.domain.message.MsgRecord;
import picocli.CommandLine.Command;
import picocli.CommandLine.Option;
import picocli.CommandLine.Parameters;

import java.util.concurrent.Callable;

/**
 * mailbus-j CLI skeleton — mirrors the Python command surface
 * (send / inbox / ack / status ...). Runs standalone or inside the Spring app.
 */
@Command(name = "mailbus", mixinStandardHelpOptions = true, version = "mailbus-j 0.1.0-SNAPSHOT",
        subcommands = {MailbusCommand.SendCommand.class, MailbusCommand.InboxCommand.class, MailbusCommand.AckCommand.class})
public class MailbusCommand {

    public static class BaseCommand {
        protected InboxService inbox;

        public void setInbox(InboxService inbox) {
            this.inbox = inbox;
        }
    }

    @Command(name = "send", description = "Push a message into an agent's inbox")
    public static class SendCommand extends BaseCommand implements Callable<Integer> {

        @Parameters(index = "0", description = "target agent id") String agent;
        @Option(names = "--msg", required = true, description = "message content") String msg;
        @Option(names = "--from", defaultValue = "system", description = "sender id") String from;

        @Override
        public Integer call() {
            MsgRecord r = inbox.send(agent, from, msg);
            System.out.printf("sent %s -> %s (%s)%n", r.id(), r.toAgent(), r.state());
            return 0;
        }
    }

    @Command(name = "inbox", description = "List pending messages of an agent")
    public static class InboxCommand extends BaseCommand implements Callable<Integer> {

        @Parameters(index = "0") String agent;

        @Override
        public Integer call() {
            inbox.inbox(agent).forEach(r ->
                    System.out.printf("%s  %-9s %s  %s%n", r.createdAt(), r.state(), r.fromAgent(), r.content()));
            return 0;
        }
    }

    @Command(name = "ack", description = "Acknowledge a message by id")
    public static class AckCommand extends BaseCommand implements Callable<Integer> {

        @Parameters(index = "0") String messageId;

        @Override
        public Integer call() {
            return inbox.acknowledge(messageId).map(r -> {
                System.out.printf("acked %s (%s)%n", r.id(), r.state());
                return 0;
            }).orElseGet(() -> {
                System.err.println("not found: " + messageId);
                return 1;
            });
        }
    }
}
