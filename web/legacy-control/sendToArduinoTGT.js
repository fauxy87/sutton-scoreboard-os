		// Simple function to submit the current score values to the PHP script that updates the Arduino
		function submitForm(){
			var formData2 = padToSend(total, 3) + padToSend(wickets, 1) + padToSend(overs, 2) + padToSend(runsreq, 3) + padToSend(target, 3) + padToSend(batsa, 3) + padToSend(batsb, 3) + padToSend(batsanum, 2) + padToSend(batsbnum, 2) + padToSend(lastwkt, 3)  + padToSend(pship, 3) + padToSend(dltarget, 3) + padToSend(lastman, 3); 
			//If runsreq & target are switched, remember to update index.html to load them in the correct order, & also scoreboard.php


//			var formData2 = padToSend(total, 3) + padToSend(wickets, 1) + padToSend(overs, 2) + padToSend(batsa, 3) + padToSend(batsb, 3) + padToSend(target, 3) + padToSend(dltarget, 3) + padToSend(batsanum, 2) + padToSend(batsbnum, 2); 


            $.ajax({
                type: "GET",
                url: "scoreboardTGT.php?data=" + formData2,
                cache: false,
                success: function () {},
                error: function () {}
            });
        }