start:
	sudo docker compose up --build --detach
	sudo docker compose kill --signal SIGKILL Dummy-Server
	sudo docker compose rm Dummy-Server --force --stop
	sudo docker compose logs --follow

stop:
	sudo docker compose kill --signal SIGTERM Load-Balancer
	sudo docker compose wait Load-Balancer
	sudo docker compose down --remove-orphans

setup:
	@sudo chmod 777 /var/run/docker.sock	

rm:
	@sudo docker kill $$(sudo docker ps -a -q)
	@sudo docker rm $$(sudo docker ps -a -q)

analysis :
	@python3 Analysis/Analysis.py

build-images:
	cd server && docker build -t server:v1 .

up: build-images
	sudo docker compose up --build -d

clean:
	sudo docker compose down --timeout 100 --volumes --remove-orphans
	sudo docker system prune -f
