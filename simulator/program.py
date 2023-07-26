from config import *
from object.objects import *
from simulator.logger import Logger
from simulator.tools import *
import math


class Program:
    def __init__(self):
        self.graph = Graph(OD_MATRIX)
        print("Graph constructed")
        self.vehicleTable = Vehicle_Table(VEHICLES, self.graph)
        print("Vehicle Table constructed")
        self.terminalTable = Terminal_Table(TERMINALS, self.graph)
        print("Terminal Table constructed")
        self.orderTable = OrderTable(ORDERS, self.graph)
        print("Order Table constructed", end="\n\n")
        self.logger = Logger()

    def travel_time(self, _from, _to):
        return math.ceil(self.graph.get_edge(_from, _to).time)

    def travel_distance(self, _from, _to):
        return self.graph.get_length(_from, _to)

    def simulator(self):
        print("Simulation ongoing..")
        self.logger.order_result_init(ORDER_RESULT_DIR)

        left = []

        for group in range(ORDER_GROUP_SIZE):
            batch = self.orderTable.table[group]
            if not batch:
                continue

            batch.extend(left)

            print(f"\tbatch {group}.. ", end='')
            self.batch_alloc(batch, group)
            self.logger.write_order(group * 60 * 6)
            print("done")

            left = []
            for order in batch:
                if order.serviced: # or order.group + 12 <= group
                    continue
                left.append(order)

        self.logger.order_result_init("results/final.csv")
        self.logger.write_order(WEEK)
        self.logger.init_veh_result("results/veh_results.csv")
        total_cost = 0
        for veh in self.vehicleTable.table:
            veh_tc = self.logger.write_veh_result(veh, veh.veh_num)
            total_cost += veh_tc
        print(f"\tTotal Cost: {total_cost}")



    def batch_alloc(self, batch:list[Order], cur_batch):

        def start_time(veh, order):
            e = self.graph.get_edge(veh.start_center, order.dest_id)
            if e.time == -1.0:
                return MAX

            arrival_time = int(math.ceil(e.time) + veh.free_time)
            return can_time_cal(arrival_time, order.start, order.end)

        allocated = False
        while not allocated:
            allocated = False

            for veh in self.vehicleTable.table:
                batch.sort(key=lambda order: (start_time(veh, order), -order.cbm))
                allocated |= self.veh_cycle(veh, batch, cur_batch)

    """
        cur_batch : 0,1,2,3,4,5,6,7
    """


    def veh_cycle(self, veh:Vehicle, batch, cur_batch):

        ret = False


        left = veh.capa
        when = veh.free_time
        where = veh.start_center
        terminal = -1

        arrival_time = -1; start_time=-1

        # First order selection
        for order in batch:
            if order.serviced or left < order.cbm or \
            self.travel_time(where, order.terminal_id) < 0 or \
            self.travel_time(order.terminal_id, order.dest_id) < 0:
                continue

            arrival_time = when + self.travel_time(where, order.terminal_id) + \
                           self.travel_time(order.terminal_id, order.dest_id)
            start_time = can_time_cal(arrival_time, order.start, order.end)

            if cur_batch != LAST_BATCH and start_time - arrival_time > HOUR*6:
                continue

            # 작업 끝나는 시간 > 작업 할당시간 + 72시간
            if start_time > MAX_START_TIME: continue
            if start_time + order.load > (order.group + 12) * 6 * 60: continue

            # to terminal
            terminal = order.terminal_id
            travel_time = self.travel_time(where, order.terminal_id)
            when += travel_time
            distance = self.travel_distance(where, terminal)
            where = order.terminal_id
            veh = self.update_vehicle(veh, order, distance, travel_time, terminal=True)
            self.logger.add_order(veh.veh_num, STRING_NULL, self.graph.idx2id(terminal), when, 0, 0, when)

            # first order
            when = start_time + order.load
            where = order.dest_id
            travel_time = self.travel_distance(terminal, where)
            distance = travel_time
            veh = self.update_vehicle(veh, order, distance, travel_time, terminal=False,
                                      start_time=start_time, arrival_time=arrival_time)
            self.logger.add_order(veh.veh_num, order.order_id, self.graph.idx2id(order.dest_id), arrival_time,
                                  start_time - arrival_time, order.load, when)
            order.serviced = True
            left -= order.cbm
            ret |= True
            break

        while True:
            order = self.next_order(batch = batch, veh = veh, where = where, when = when,
                                    left = left, terminal = terminal, carry_over= (cur_batch != LAST_BATCH))
            if order is None: break # can't allocate anymore

            if order.dest_id != where:
                arrival_time = when + self.travel_time(where, order.dest_id)
                start_time = can_time_cal(arrival_time, order.start, order.end)
                when = start_time + order.load

            distance = self.travel_distance(where, order.dest_id)
            travel_time = self.travel_time(where, order.dest_id)
            veh = self.update_vehicle(veh, order, distance, travel_time, terminal=False,
                                      start_time=start_time, arrival_time=arrival_time)
            where = order.dest_id
            left -= order.cbm
            order.serviced = True
            self.logger.add_order(veh.veh_num, order.order_id, self.graph.idx2id(order.dest_id), arrival_time,
                             start_time - arrival_time, order.load, when)

        veh.free_time = when
        veh.start_center = where

        return ret

    def next_order(self, batch: list[Order], veh: Vehicle,
                   where: int, when: int, left:int, terminal:int,
                   carry_over:bool):

        ret = None
        best_start = MAX
        for order in batch:
            if  order.serviced or left < order.cbm or terminal != order.terminal_id or \
                self.travel_time(where, order.dest_id) < 0:
                continue

            arrival_time = when + self.travel_time(where, order.dest_id)
            start_time = can_time_cal(arrival_time, order.start, order.end)

            if carry_over and start_time - arrival_time > HOUR * 6:
                continue

            if start_time < MAX_START_TIME and start_time < best_start and \
                    start_time + order.load <= (order.group + 12) * 6 * 60:
                ret = order
                best_start = start_time

        return ret

    def update_vehicle(self, veh, order, distance, travel_time, terminal=True, start_time=None, arrival_time=None):
        veh.travel_distance += distance
        veh.travel_time += travel_time
        veh.work_time += travel_time

        if not terminal:
            veh.volume += order.cbm
            veh.work_time += order.load
            veh.count += 1
            veh.service_time += order.load
            veh.waiting_time += start_time - arrival_time

        return veh

