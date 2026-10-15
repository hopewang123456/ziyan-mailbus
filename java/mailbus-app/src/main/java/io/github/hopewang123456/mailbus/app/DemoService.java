package io.github.hopewang123456.mailbus.app;

import io.github.hopewang123456.mailbus.domain.message.MsgRecord;

import java.util.ArrayList;
import java.util.List;

/**
 * Zero-dependency demo chain — the Java counterpart of `mailbus demo`:
 * create -> dispatch(send) -> execute(ack) -> accept -> archive,
 * printed step by step against a fresh demo agent.
 */
public class DemoService {

    private final InboxService inbox;
    private final ArchiveService archive;

    public DemoService(InboxService inbox, ArchiveService archive) {
        this.inbox = inbox;
        this.archive = archive;
    }

    public List<String> run() {
        List<String> lines = new ArrayList<>();
        String agent = "agent-demo";
        lines.add("== mailbus-j demo: create -> send -> execute -> accept -> archive ==");

        lines.add("[1] create+send");
        MsgRecord m = inbox.send(agent, "demo", "demo 工单：验证 mailbus-j 消息全链路");
        lines.add("    " + m.id() + " -> " + agent + " state=" + m.state());

        lines.add("[2] execute (ack by the demo agent)");
        MsgRecord done = inbox.acknowledge(m.id()).orElseThrow();
        lines.add("    state=" + done.state());

        lines.add("[3] accept -> archive");
        ArchiveService.Outcome out = archive.archiveSettled(agent);
        lines.add("    archived=" + out.archived() + " " + out.ids());

        lines.add("[4] verify");
        lines.add("    unread now: " + inbox.unreadCount(agent));
        lines.add("== demo complete ==");
        return lines;
    }
}
