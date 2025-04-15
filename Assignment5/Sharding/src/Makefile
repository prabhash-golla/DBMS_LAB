start:
	docker compose up --build --detach
	docker compose kill --signal SIGKILL Dummy-Server
	docker compose rm Dummy-Server --force --stop
	docker compose logs --follow

stop:
	docker compose kill --signal SIGTERM Load-Balancer
	docker compose wait Load-Balancer
	docker compose down --remove-orphans
	
build-images:
	cd server && docker build -t server:v1 .

up: build-images
	docker compose up --build -d

clean:
	docker compose down --timeout 100 --volumes --remove-orphans
	docker system prune -f
