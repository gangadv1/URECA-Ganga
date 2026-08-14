`timescale 1ns/1ps
module tb_relay_bp_first_success_arbiter_n2;
 logic clk=0,rst=1,start=0,c0=0,c1=0,f0=0,f1=0;logic[31:0]cycle_count=0,frame_id=0,it0=3,it1=5;logic signed[31:0]w0=-10,w1=-20;logic[1:0]l0=1,l1=2;logic done,failed,valid,win;logic signed[31:0]weight;logic[31:0]iterations,first_cycle,wframe;logic[1:0]legs;logic same;integer cases=0;
 always #5 clk=~clk;always @(posedge clk)if(!rst)cycle_count<=cycle_count+1;
 relay_bp_first_success_arbiter_n2 #(.LW(2))dut(.clk,.rst,.start,.cycle_count,.frame_id,.candidate0(c0),.candidate1(c1),.failed0(f0),.failed1(f1),.weight0(w0),.weight1(w1),.iterations0(it0),.iterations1(it1),.legs0(l0),.legs1(l1),.global_done(done),.global_failed(failed),.global_candidate_valid(valid),.winning_engine_id(win),.winning_weight(weight),.winning_iteration_count(iterations),.winning_leg_count(legs),.first_success_cycle(first_cycle),.winning_frame_id(wframe),.same_cycle_success(same));
 task begin_case(input[31:0]fid);begin @(negedge clk);c0=0;c1=0;f0=0;f1=0;frame_id=fid;start=1;@(negedge clk);start=0;cases=cases+1;end endtask
 initial begin repeat(2)@(posedge clk);rst=0;
  begin_case(1);@(negedge clk)c0=1;@(negedge clk)c0=0;c1=1;@(negedge clk)c1=0;#1;if(!done||!valid||failed||win||weight!=-10||wframe!=1)$fatal(1,"engine0-first failed");
  begin_case(2);@(negedge clk)c1=1;@(negedge clk)c1=0;f0=1;#1;if(!done||win!=1||weight!=-20||wframe!=2)$fatal(1,"engine1-first/loser-fails failed");
  begin_case(3);@(negedge clk)c0=1;c1=1;@(negedge clk)c0=0;c1=0;#1;if(!done||win||!same||weight!=-10)$fatal(1,"same-cycle priority failed");
  begin_case(4);@(negedge clk)f0=1;repeat(3)@(negedge clk);if(done)$fatal(1,"premature fail after engine0 failure");c1=1;@(negedge clk)c1=0;#1;if(!done||failed||!valid||!win)$fatal(1,"fail0 then success1 failed");
  begin_case(5);@(negedge clk)f1=1;repeat(2)@(negedge clk);if(done)$fatal(1,"premature fail after engine1 failure");c0=1;@(negedge clk)c0=0;#1;if(!done||failed||!valid||win)$fatal(1,"fail1 then success0 failed");
  begin_case(6);@(negedge clk)f0=1;f1=1;@(negedge clk);#1;if(!done||!failed||valid)$fatal(1,"same-cycle both fail failed");
  begin_case(7);@(negedge clk)f0=1;repeat(2)@(negedge clk);if(done)$fatal(1,"premature staggered fail");f1=1;@(negedge clk);#1;if(!done||!failed||valid)$fatal(1,"staggered both fail failed");
  $display("FIRST_SUCCESS_ARBITER_RESULT cases=%0d same_cycle=1 asymmetric_success=4 both_fail=2 failures=0",cases);$finish;
 end
endmodule
