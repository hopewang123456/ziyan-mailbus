// @vitest-environment jsdom
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FloorSlab } from "../twin/FloorSlab";
import { chooseDoorWall, elevatorSpot, getDoorCenter, lineFree, planPath, pointBlocked } from "../twin/pathfind";
import type { Floor, OfficeSite } from "../twin/types";

const layouts = import.meta.glob<OfficeSite>("../../../config/office-layout.json", { eager: true, import: "default" });
const site = layouts["../../../config/office-layout.json"];
const floors: Floor[] = site.floors.map((floor) => ({
  ...floor,
  rooms: floor.rooms.map((room) => ({
    ...room,
    seats: room.seats.map((seat) => ({ ...seat, agent: null })),
  })),
}));

function renderFloor(floor: Floor) {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(
    <FloorSlab floor={floor} index={0} active dimmed={false} selectedSeatId={null}
      onSelectFloor={() => {}} onSelectSeat={() => {}} />,
  );
  return root;
}

describe("办公室布局与家具回归", () => {
  it("两层房间均不重叠，2F 休息区止于 x=800 且保留 22 个原工位", () => {
    expect(floors.flatMap((floor) => floor.rooms.flatMap((room) => room.seats))).toHaveLength(22);
    const lounge = floors[1].rooms.find((room) => room.kind === "lounge")!;
    expect([lounge.x, lounge.y, lounge.w, lounge.h]).toEqual([60, 580, 740, 260]);
    for (const floor of floors) {
      for (let i = 0; i < floor.rooms.length; i += 1) {
        const a = floor.rooms[i];
        for (const b of floor.rooms.slice(i + 1)) {
          expect(a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y).toBe(false);
        }
        for (const seat of a.seats) {
          expect(seat.x - 46).toBeGreaterThan(a.x);
          expect(seat.x + 46).toBeLessThan(a.x + a.w);
          expect(seat.y - 26).toBeGreaterThan(a.y);
          expect(seat.y + 26).toBeLessThan(a.y + a.h);
        }
      }
    }
  });

  it("每间休息区只有完整的一套沙发茶几，杯子和新增书本落在桌面内", () => {
    for (const floor of floors) {
      const root = renderFloor(floor);
      const lounge = root.querySelector(".room-lounge")!;
      expect(lounge.querySelectorAll(".sofa-main")).toHaveLength(1);
      expect(lounge.querySelectorAll(".coffee-table")).toHaveLength(1);
      expect(lounge.querySelector(".prop-sofa, .prop-ctable")).toBeNull();
      expect((lounge.querySelector(".table-mug") as HTMLElement).style.top).toBe("54px");
      expect(lounge.querySelector(".desk-notes")).not.toBeNull();
    }
  });

  it("前台柜台不再覆盖工位/离座点，2F 盆栽叶冠与盆底均在房内", () => {
    const reception = floors[0].rooms.find((room) => room.kind === "reception")!;
    expect(pointBlocked(floors[0], reception.x + reception.w / 2, reception.y + reception.h / 2 + 60)).toBe(true);
    for (const seat of reception.seats) {
      expect(pointBlocked(floors[0], seat.x, seat.y + 50)).toBe(false);
    }
    const root = renderFloor(floors[1]);
    const room = floors[1].rooms.find((r) => r.kind === "lounge")!;
    const plant = root.querySelector(".room-lounge .plant.p3") as HTMLElement;
    const top = room.h / 2 + Number.parseFloat(plant.style.top);
    expect(top - 18).toBeGreaterThanOrEqual(0);
    expect(top + 30).toBeLessThanOrEqual(room.h);
  });

  it("门洞、设施接近点与电梯均可站立，电梯不再位于房间内", () => {
    for (const floor of floors) {
      const elevator = elevatorSpot(floor);
      expect(pointBlocked(floor, elevator.x, elevator.y)).toBe(false);
      expect(floor.rooms.some((room) => elevator.x > room.x && elevator.x < room.x + room.w && elevator.y > room.y && elevator.y < room.y + room.h)).toBe(false);
      for (const room of floor.rooms) {
        const door = getDoorCenter(room, chooseDoorWall(room, floor.rooms));
        expect(pointBlocked(floor, door.x, door.y), room.room_id).toBe(false);
        if (room.kind !== "lounge") continue;
        const cx = room.x + room.w / 2;
        const cy = room.y + room.h / 2;
        for (const point of [
          { x: room.x + room.w - 49, y: room.y + 76 },
          { x: room.x + 78, y: room.y + room.h - 42 },
          { x: cx - 130, y: cy + 6 }, { x: cx + 130, y: cy + 6 },
          { x: cx - 76, y: cy + 78 }, { x: cx + 76, y: cy + 78 },
        ]) {
          expect(pointBlocked(floor, point.x, point.y)).toBe(false);
          const path = planPath(floor, elevator, point);
          expect(path, `${room.room_id}: ${JSON.stringify(point)}`).not.toBeNull();
          for (let i = 1; i < path!.length; i += 1) expect(lineFree(floor, path![i - 1], path![i])).toBe(true);
        }
        expect(pointBlocked(floor, cx, cy + 70)).toBe(true);
      }
    }
  });

  it("所有工位离座点均能抵达本层电梯，不穿越家具或墙", () => {
    for (const floor of floors) {
      for (const seat of floor.rooms.flatMap((room) => room.seats)) {
        const path = planPath(floor, { x: seat.x, y: seat.y + 50 }, elevatorSpot(floor));
        expect(path, seat.seat_id).not.toBeNull();
        for (let i = 1; i < path!.length; i += 1) expect(lineFree(floor, path![i - 1], path![i])).toBe(true);
      }
    }
  });

  it("同一 floor_id 的布局变更不会复用旧障碍网格", () => {
    const floor = floors[1];
    expect(pointBlocked(floor, 430, 710)).toBe(true);
    const changed = { ...floor, rooms: floor.rooms.filter((room) => room.kind !== "lounge") };
    expect(pointBlocked(changed, 430, 710)).toBe(false);
  });
});
